"""
BtcTurk Exchange Client
Asyncio-based client for BtcTurk REST API and WebSocket feed.
Supports public/private REST endpoints and WebSocket channels.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp
import websockets
from dotenv import load_dotenv
from websockets.client import WebSocketClientProtocol

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class BtcturkClient:
    """
    BtcTurk exchange client with REST and WebSocket support.
    
    Features:
    - REST API v1/v2 with HMAC authentication
    - WebSocket public channels (trade, orderbook, ticker)
    - WebSocket private authentication and user events
    - Local orderbook management with full snapshot + diff merge
    - Automatic reconnection and heartbeat monitoring
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        ws_public_key: Optional[str] = None,
        ws_private_key: Optional[str] = None,
    ):
        """
        Initialize BtcTurk client.
        
        IMPORTANT: BtcTurk requires SEPARATE API keys for REST and WebSocket!
        
        To create WebSocket keys:
        1. Go to BtcTurk > ACCOUNT > API Access
        2. Select "WebSocket" (not REST) when creating keys
        3. Enter your IP address
        4. You'll get separate Public/Private keys for WebSocket
        
        Args:
            api_key: REST API Public key (if None, reads from BTC_TURK_Public_Key env var)
            api_secret: REST API Private key (if None, reads from BTC_TURK_Private_Key env var)
            ws_public_key: WebSocket Public key (if None, reads from BTC_TURK_WS_Public_Key env var)
            ws_private_key: WebSocket Private key (if None, reads from BTC_TURK_WS_Private_Key env var)
        """
        # REST API credentials
        self.api_key = (
            api_key or 
            os.getenv("BTC_TURK_Public_Key") or 
            os.getenv("BTC_TURK_API_KEY")
        )
        self.api_secret = (
            api_secret or 
            os.getenv("BTC_TURK_Private_Key") or 
            os.getenv("BTC_TURK_API_SECRET")
        )
        
        # WebSocket credentials (MUST be separate keys created with "WebSocket" type!)
        self.ws_public_key = (
            ws_public_key or 
            os.getenv("BTC_TURK_WS_Public_Key") or
            self.api_key  # Fallback to REST key for backward compatibility
        )
        self.ws_private_key = (
            ws_private_key or 
            os.getenv("BTC_TURK_WS_Private_Key") or
            self.api_secret  # Fallback to REST key for backward compatibility
        )
        
        # Endpoints
        self.rest_base_url = "https://api.btcturk.com"
        self.ws_url = "wss://ws-feed-pro.btcturk.com/"
        
        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        
        # WebSocket
        self.ws: Optional[WebSocketClientProtocol] = None
        self.running = False
        self.ws_authenticated = False
        
        # Monitoring
        self.last_msg_ts = 0.0
        self.latency_rtt = 0.0  # Ping-pong RTT in milliseconds
        self.latency_event = 0.0  # Event timestamp latency in milliseconds
        
        # Subscriptions (to restore on reconnect)
        self.subscriptions: List[Dict[str, Any]] = []
        
        # Local orderbook state: {pair: {"bids": [(price, qty), ...], "asks": [...]}}
        self.orderbooks: Dict[str, Dict[str, List[Tuple[float, float]]]] = {}
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        
        # Nonce counter for WS authentication (start from a higher number)
        self._ws_nonce = 3000
        
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            async with self._session_lock:
                if self.session is None or self.session.closed:
                    self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close all connections and sessions."""
        await self.disconnect()
        if self.session and not self.session.closed:
            await self.session.close()
    
    # =========================================================================
    # WEBSOCKET - CONNECTION AND MESSAGE LOOP
    # =========================================================================
    
    async def connect(self, on_message: Optional[Callable[[Any], None]] = None):
        """
        Connect to WebSocket and start message loop.
        
        Args:
            on_message: Optional callback to receive all parsed messages
        """
        self.running = True
        self.last_msg_ts = time.time()
        
        # Start background tasks
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_task_loop())
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._ping_task_loop())
        
        retry_delay = 1.0
        max_retry_delay = 60.0
        
        while self.running:
            try:
                logger.info(f"Connecting to BtcTurk WebSocket: {self.ws_url}")
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=None,
                    close_timeout=10,
                ) as ws:
                    self.ws = ws
                    logger.info("BtcTurk WebSocket connected")
                    
                    # Reset retry delay on successful connection
                    retry_delay = 1.0
                    
                    # Note: BtcTurk WebSocket authentication is optional for public channels
                    # We skip authentication and just subscribe to public channels
                    # If you need private user events, implement authentication separately
                    
                    # Restore subscriptions
                    await self._restore_subscriptions()
                    
                    # Message loop
                    async for raw_msg in ws:
                        receive_time = time.time()
                        self.last_msg_ts = receive_time
                        
                        try:
                            msg = json.loads(raw_msg)
                            
                            # Handle message internally
                            await self._handle_message(msg)
                            
                            # Call external callback if provided
                            if on_message:
                                try:
                                    on_message(msg)
                                except Exception as e:
                                    logger.error(f"Error in on_message callback: {e}")
                        
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse WS message: {e}")
                        except Exception as e:
                            logger.error(f"Error handling WS message: {e}")
            
            except asyncio.CancelledError:
                logger.info("WebSocket connection cancelled")
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            
            finally:
                self.ws = None
                self.ws_authenticated = False
            
            # Reconnect logic
            if self.running:
                logger.info(f"Reconnecting in {retry_delay:.1f} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, max_retry_delay)
        
        logger.info("WebSocket connection closed")
    
    async def disconnect(self):
        """Disconnect from WebSocket and stop background tasks."""
        logger.info("Disconnecting WebSocket...")
        self.running = False
        
        # Cancel background tasks
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            finally:
                self.ws = None
    
    async def _restore_subscriptions(self):
        """Restore subscriptions after reconnect."""
        for sub in self.subscriptions:
            try:
                await self._send_ws_message(sub)
                logger.info(f"Restored subscription: {sub}")
            except Exception as e:
                logger.error(f"Failed to restore subscription {sub}: {e}")
    
    async def _send_ws_message(self, message: Any):
        """Send a message to WebSocket."""
        if self.ws:
            try:
                await self.ws.send(json.dumps(message))
            except Exception as e:
                logger.warning(f"Cannot send message: {e}")
        else:
            logger.warning("Cannot send message, WebSocket not connected")
    
    # =========================================================================
    # WEBSOCKET - BACKGROUND TASKS
    # =========================================================================
    
    async def _heartbeat_task_loop(self):
        """Monitor connection health and force reconnect if needed."""
        heartbeat_interval = 5.0
        timeout_threshold = 45.0
        
        while self.running:
            try:
                await asyncio.sleep(heartbeat_interval)
                
                now = time.time()
                elapsed = now - self.last_msg_ts
                
                if elapsed > timeout_threshold:
                    logger.warning(
                        f"No message received for {elapsed:.1f}s, forcing reconnect"
                    )
                    if self.ws and not self.ws.closed:
                        await self.ws.close()
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
    
    async def _ping_task_loop(self):
        """Send periodic pings to measure RTT latency."""
        ping_interval = 5.0  # Send ping every 5 seconds
        
        while self.running:
            try:
                await asyncio.sleep(ping_interval)
                
                if not self.ws:
                    continue
                
                # Use WebSocket native ping frame for RTT measurement
                start_time = time.time()
                pong_waiter = await self.ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=5.0)
                rtt_ms = (time.time() - start_time) * 1000
                
                # Update latency with EMA (Exponential Moving Average)
                alpha = 0.3  # Smoothing factor
                if self.latency_rtt == 0:
                    self.latency_rtt = rtt_ms
                else:
                    self.latency_rtt = alpha * rtt_ms + (1 - alpha) * self.latency_rtt
                
                logger.debug(f"BTCTurk WebSocket ping RTT: {rtt_ms:.1f}ms (smoothed={self.latency_rtt:.1f}ms)")
            
            except asyncio.TimeoutError:
                logger.debug("BTCTurk ping timeout")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"BTCTurk ping error: {e}")
    
    def _calculate_latency(self, event_timestamp_ms: float):
        """
        Calculate latency from WebSocket event timestamp.
        
        Args:
            event_timestamp_ms: Event timestamp in milliseconds (Unix time)
        """
        try:
            # Sanity check: reasonable timestamp (after year 2001)
            if not event_timestamp_ms or event_timestamp_ms < 1000000000000:
                return
            
            # Get current time in milliseconds
            current_time_ms = time.time() * 1000
            
            # Calculate latency: now - event_timestamp
            # Use abs() because clock skew can make event timestamp slightly in future
            latency = abs(current_time_ms - event_timestamp_ms)
            
            # Only update if latency is reasonable (0-10000ms = 0-10 seconds)
            if 0 <= latency <= 10000:
                # Apply EMA smoothing if we already have a value
                if self.latency_event > 0:
                    alpha = 0.3
                    self.latency_event = alpha * latency + (1 - alpha) * self.latency_event
                else:
                    self.latency_event = latency
                
                logger.debug(f"BTCTurk event latency: {latency:.2f}ms (smoothed: {self.latency_event:.2f}ms)")
        
        except Exception as e:
            logger.error(f"Latency calculation error: {e}")
            pass
    
    # =========================================================================
    # WEBSOCKET - MESSAGE ROUTER
    # =========================================================================
    
    async def _handle_message(self, msg: Any):
        """
        Route incoming WebSocket messages to appropriate handlers.
        
        Message format: [typeCode, payload]
        """
        if not isinstance(msg, list) or len(msg) < 2:
            logger.debug(f"Unknown message format: {msg}")
            return
        
        code = msg[0]
        payload = msg[1] if len(msg) > 1 else {}
        
        # Orderbook messages
        if code == 431:  # Full orderbook snapshot
            self._handle_orderbook_full(payload)
        elif code == 432:  # Orderbook diff
            self._handle_orderbook_diff(payload)
        
        # Trade messages
        elif code == 422:  # Single trade
            self._handle_trade(payload)
        elif code == 421:  # Trade list (initial)
            logger.debug(f"Trade list received: {len(payload.get('items', []))} trades")
        
        # Ticker messages
        elif code in (401, 402):
            self._handle_ticker(payload)
        
        # User events
        elif code in (423, 441, 451, 452, 453):
            self._handle_user_event(code, payload)
        
        # Login result
        elif code == 114:
            self._handle_login_result(payload)
        
        # Subscribe/unsubscribe result
        elif code == 151:
            logger.debug(f"Subscribe result: {payload}")
        
        # Generic result
        elif code == 100:
            logger.debug(f"Result message: {payload}")
        
        else:
            logger.debug(f"Unhandled message type {code}: {payload}")
    
    def _handle_orderbook_full(self, payload: Dict[str, Any]):
        """Handle full orderbook snapshot (type 431)."""
        try:
            # Type 431 format: {PS, BO, AO}
            pair = payload.get("PS")  # Pair symbol
            if not pair:
                logger.warning(f"Orderbook full missing pair symbol")
                return
            
            # Parse bids and asks
            bids = []
            asks = []
            
            # Bids: BO array with {P: price, A: amount}
            for bid in payload.get("BO", []):
                price = float(bid.get("P", 0))
                qty = float(bid.get("A", 0))
                if price > 0 and qty > 0:
                    bids.append((price, qty))
            
            # Asks: AO array with {P: price, A: amount}
            for ask in payload.get("AO", []):
                price = float(ask.get("P", 0))
                qty = float(ask.get("A", 0))
                if price > 0 and qty > 0:
                    asks.append((price, qty))
            
            # Sort: bids descending, asks ascending
            bids.sort(reverse=True)
            asks.sort()
            
            self.orderbooks[pair] = {"bids": bids, "asks": asks}
            logger.debug(
                f"Orderbook full for {pair}: "
                f"{len(bids)} bids, {len(asks)} asks"
            )
        
        except Exception as e:
            logger.error(f"Error handling orderbook full: {e}")
    
    def _handle_orderbook_diff(self, payload: Dict[str, Any]):
        """Handle orderbook difference (type 432)."""
        try:
            pair = payload.get("PS")
            if not pair or pair not in self.orderbooks:
                return
            
            ob = self.orderbooks[pair]
            
            # Update bids: BO array with {P: price, A: amount}
            for change in payload.get("BO", []):
                price = float(change.get("P", 0))
                qty = float(change.get("A", 0))
                
                if price <= 0:
                    continue
                
                # Remove existing level
                ob["bids"] = [(p, q) for p, q in ob["bids"] if p != price]
                
                # Add new level if qty > 0
                if qty > 0:
                    ob["bids"].append((price, qty))
                    ob["bids"].sort(reverse=True)
            
            # Update asks: AO array with {P: price, A: amount}
            for change in payload.get("AO", []):
                price = float(change.get("P", 0))
                qty = float(change.get("A", 0))
                
                if price <= 0:
                    continue
                
                # Remove existing level
                ob["asks"] = [(p, q) for p, q in ob["asks"] if p != price]
                
                # Add new level if qty > 0
                if qty > 0:
                    ob["asks"].append((price, qty))
                    ob["asks"].sort()
        
        except Exception as e:
            logger.error(f"Error handling orderbook diff: {e}")
    
    def _handle_trade(self, payload: Dict[str, Any]):
        """Handle trade message (type 422)."""
        try:
            pair = payload.get("PS")
            price = payload.get("P")
            amount = payload.get("A")
            side = payload.get("S")  # 0=buy, 1=sell
            trade_timestamp = payload.get("D")  # Unix timestamp in milliseconds
            
            # Calculate event latency if timestamp available
            if trade_timestamp:
                # Convert to float if it's a string
                ts_ms = float(trade_timestamp) if isinstance(trade_timestamp, str) else trade_timestamp
                self._calculate_latency(ts_ms)
                logger.debug(
                    f"Trade {pair}: {side} {amount} @ {price} (event latency={self.latency_event:.2f}ms)"
                )
        
        except Exception as e:
            logger.error(f"Error handling trade: {e}")
    
    def _handle_ticker(self, payload: Dict[str, Any]):
        """Handle ticker message (types 401, 402)."""
        try:
            pair = payload.get("PS")
            last = payload.get("L")
            bid = payload.get("B")
            ask = payload.get("A")
            
            logger.debug(
                f"Ticker {pair}: last={last}, bid={bid}, ask={ask}"
            )
        
        except Exception as e:
            logger.error(f"Error handling ticker: {e}")
    
    def _handle_user_event(self, code: int, payload: Dict[str, Any]):
        """
        Handle user-specific events (types 423, 441, 451, 452, 453).
        
        These events are only received after successful WebSocket authentication.
        """
        if code == 423:
            # UserTrade - sent when user's order is matched
            self._handle_user_trade(payload)
        elif code == 441:
            # UserOrderMatch - sent when user's order is executed
            self._handle_user_order_match(payload)
        elif code == 451:
            # OrderInsert - sent when user's order is added to the system
            self._handle_order_insert(payload)
        elif code == 452:
            # OrderDelete - sent when user's order is deleted from the system
            self._handle_order_delete(payload)
        elif code == 453:
            # OrderUpdate - sent when user's order is updated in the system
            self._handle_order_update(payload)
        else:
            logger.warning(f"Unknown user event type {code}: {payload}")
    
    def _handle_user_trade(self, payload: Dict[str, Any]):
        """
        Handle UserTrade event (type 423).
        
        Sent when user's order is matched.
        """
        try:
            trade_info = {
                "id": payload.get("id"),
                "orderId": payload.get("orderId"),
                "timestamp": payload.get("timestamp"),
                "pair": f"{payload.get('numeratorSymbol')}{payload.get('denominatorSymbol')}",
                "amount": payload.get("amount"),
                "price": payload.get("price"),
                "orderType": payload.get("orderType"),
                "fee": payload.get("fee"),
                "tax": payload.get("tax"),
                "orderClientId": payload.get("orderClientId"),
            }
            logger.info(f"🔔 UserTrade: {trade_info['orderType']} {trade_info['amount']} @ {trade_info['price']} (Trade ID: {trade_info['id']}, Order ID: {trade_info['orderId']})")
            logger.debug(f"Full UserTrade data: {payload}")
        except Exception as e:
            logger.error(f"Error parsing UserTrade: {e}")
            logger.error(f"Payload: {payload}")
    
    def _handle_user_order_match(self, payload: Dict[str, Any]):
        """
        Handle UserOrderMatch event (type 441).
        
        Sent when user's order is executed (contains execution details).
        """
        try:
            side = "BUY" if payload.get("isBid") else "SELL"
            method_map = {0: "LIMIT", 1: "MARKET", 2: "STOP_LIMIT"}
            method = method_map.get(payload.get("method"), "UNKNOWN")
            
            match_info = {
                "id": payload.get("id"),
                "symbol": payload.get("symbol"),
                "side": side,
                "method": method,
                "amount": payload.get("amount"),
                "price": payload.get("price"),
                "clientId": payload.get("clientId"),
                "timestamp": payload.get("timestamp"),
            }
            logger.info(f"🔔 UserOrderMatch: {match_info['side']} {match_info['method']} {match_info['amount']} @ {match_info['price']} on {match_info['symbol']} (Match ID: {match_info['id']})")
            logger.debug(f"Full UserOrderMatch data: {payload}")
        except Exception as e:
            logger.error(f"Error parsing UserOrderMatch: {e}")
            logger.error(f"Payload: {payload}")
    
    def _handle_order_insert(self, payload: Dict[str, Any]):
        """
        Handle OrderInsert event (type 451).
        
        Sent when user's order is added to the system.
        """
        try:
            method_map = {0: "LIMIT", 1: "MARKET", 2: "STOP_LIMIT"}
            method = method_map.get(payload.get("method"), "UNKNOWN")
            
            order_info = {
                "id": payload.get("ID") or payload.get("id"),
                "symbol": payload.get("symbol"),
                "method": method,
                "price": payload.get("price"),
                "amount": payload.get("amount"),
                "numLeft": payload.get("numLeft"),
                "denomLeft": payload.get("denomLeft"),
                "clientId": payload.get("newOrderClientId"),
            }
            logger.info(f"✅ OrderInsert: {order_info['method']} order on {order_info['symbol']} - Amount: {order_info['amount']}, Price: {order_info['price']} (Order ID: {order_info['id']})")
            logger.debug(f"Full OrderInsert data: {payload}")
        except Exception as e:
            logger.error(f"Error parsing OrderInsert: {e}")
            logger.error(f"Payload: {payload}")
    
    def _handle_order_delete(self, payload: Dict[str, Any]):
        """
        Handle OrderDelete event (type 452).
        
        Sent when user's order is deleted from the system.
        Uses same format as OrderInsert.
        """
        try:
            method_map = {0: "LIMIT", 1: "MARKET", 2: "STOP_LIMIT"}
            method = method_map.get(payload.get("method"), "UNKNOWN")
            
            order_info = {
                "id": payload.get("ID") or payload.get("id"),
                "symbol": payload.get("symbol"),
                "method": method,
                "price": payload.get("price"),
                "amount": payload.get("amount"),
                "clientId": payload.get("newOrderClientId"),
            }
            logger.info(f"❌ OrderDelete: {order_info['method']} order on {order_info['symbol']} deleted (Order ID: {order_info['id']})")
            logger.debug(f"Full OrderDelete data: {payload}")
        except Exception as e:
            logger.error(f"Error parsing OrderDelete: {e}")
            logger.error(f"Payload: {payload}")
    
    def _handle_order_update(self, payload: Dict[str, Any]):
        """
        Handle OrderUpdate event (type 453).
        
        Sent when user's order is updated in the system.
        Uses same format as OrderInsert.
        """
        try:
            method_map = {0: "LIMIT", 1: "MARKET", 2: "STOP_LIMIT"}
            method = method_map.get(payload.get("method"), "UNKNOWN")
            
            order_info = {
                "id": payload.get("ID") or payload.get("id"),
                "symbol": payload.get("symbol"),
                "method": method,
                "price": payload.get("price"),
                "amount": payload.get("amount"),
                "numLeft": payload.get("numLeft"),
                "denomLeft": payload.get("denomLeft"),
                "clientId": payload.get("newOrderClientId"),
            }
            logger.info(f"🔄 OrderUpdate: {order_info['method']} order on {order_info['symbol']} updated - Num left: {order_info['numLeft']}, Denom left: {order_info['denomLeft']} (Order ID: {order_info['id']})")
            logger.debug(f"Full OrderUpdate data: {payload}")
        except Exception as e:
            logger.error(f"Error parsing OrderUpdate: {e}")
            logger.error(f"Payload: {payload}")
    
    def _handle_login_result(self, payload: Dict[str, Any]):
        """Handle WebSocket login result (type 114)."""
        logger.info(f"Login response payload: {payload}")
        # Check both 'ok' (lowercase) and 'OK' (uppercase), both True/1
        ok = payload.get("ok") or payload.get("OK")
        if ok is True or ok == 1:
            self.ws_authenticated = True
            logger.info("WebSocket authentication successful")
        else:
            message = payload.get("message") or payload.get("M", "Unknown error")
            logger.error(f"WebSocket authentication failed: {message}")
            logger.error(f"Full payload: {payload}")
    
    # =========================================================================
    # WEBSOCKET - AUTHENTICATION
    # =========================================================================
    
    async def authenticate_ws(self):
        """
        Authenticate WebSocket connection using HMAC signature.
        
        IMPORTANT: BtcTurk requires SEPARATE WebSocket API keys!
        
        To enable WebSocket private authentication:
        1. Go to BtcTurk > ACCOUNT > API Access
        2. Create new API keys and select "WebSocket" type (not REST)
        3. Enter your IP address
        4. Add the new keys to .env as BTC_TURK_WS_Public_Key and BTC_TURK_WS_Private_Key
        
        The WebSocket authentication uses the same HMAC signature as REST:
        - signature = HMAC-SHA256(base64_decode(privateKey), publicKey + timestamp)
        """
        if not self.ws_public_key or not self.ws_private_key:
            logger.warning("WebSocket credentials not provided, skipping auth")
            return
        
        try:
            # CRITICAL: BtcTurk WebSocket uses a FIXED nonce (not timestamp!)
            # The nonce is a counter that increments with each auth attempt
            self._ws_nonce += 1
            nonce = self._ws_nonce
            
            # Get current timestamp
            timestamp = round(time.time() * 1000)
            
            # Build base string: publicKey + nonce (as STRING!)
            base_string = f"{self.ws_public_key}{nonce}".encode("utf-8")
            
            # Decode private key from base64
            private_key_bytes = base64.b64decode(self.ws_private_key)
            
            # Create HMAC signature
            signature_bytes = hmac.new(
                private_key_bytes,
                base_string,
                hashlib.sha256,
            ).digest()
            
            # Encode signature to base64
            signature = base64.b64encode(signature_bytes).decode("utf-8")
            
            # Send login message with NONCE
            login_msg = [
                114,
                {
                    "nonce": nonce,
                    "publicKey": self.ws_public_key,
                    "signature": signature,
                    "timestamp": timestamp,
                    "type": 114,
                },
            ]
            
            await self._send_ws_message(login_msg)
            logger.info(f"WebSocket authentication request sent (nonce={nonce}, timestamp={timestamp})")
            logger.info("Waiting for authentication response...")
        
        except Exception as e:
            logger.error(f"WebSocket authentication error: {e}")
            raise
    
    # =========================================================================
    # WEBSOCKET - SUBSCRIPTIONS
    # =========================================================================
    
    async def subscribe_trade(self, pair_symbol: str):
        """Subscribe to trade channel for a pair."""
        sub_msg = [
            151,
            {
                "type": 151,
                "channel": "trade",
                "event": pair_symbol,
                "join": True,
            },
        ]
        
        await self._send_ws_message(sub_msg)
        
        # Store subscription for reconnect
        if sub_msg not in self.subscriptions:
            self.subscriptions.append(sub_msg)
        
        logger.info(f"Subscribed to trade channel: {pair_symbol}")
    
    async def subscribe_orderbook(self, pair_symbol: str):
        """Subscribe to orderbook channels (full + diff) for a pair."""
        # Subscribe to full orderbook
        full_msg = [
            151,
            {
                "type": 151,
                "channel": "orderbook",
                "event": pair_symbol,
                "join": True,
            },
        ]
        await self._send_ws_message(full_msg)
        
        if full_msg not in self.subscriptions:
            self.subscriptions.append(full_msg)
        
        # Subscribe to orderbook diff
        diff_msg = [
            151,
            {
                "type": 151,
                "channel": "obdiff",
                "event": pair_symbol,
                "join": True,
            },
        ]
        await self._send_ws_message(diff_msg)
        
        if diff_msg not in self.subscriptions:
            self.subscriptions.append(diff_msg)
        
        # Initialize orderbook state
        if pair_symbol not in self.orderbooks:
            self.orderbooks[pair_symbol] = {"bids": [], "asks": []}
        
        logger.info(f"Subscribed to orderbook channels: {pair_symbol}")
    
    async def subscribe_ticker(self, pair_symbol: str):
        """Subscribe to ticker channel for a pair."""
        sub_msg = [
            151,
            {
                "type": 151,
                "channel": "ticker",
                "event": pair_symbol,
                "join": True,
            },
        ]
        
        await self._send_ws_message(sub_msg)
        
        if sub_msg not in self.subscriptions:
            self.subscriptions.append(sub_msg)
        
        logger.info(f"Subscribed to ticker channel: {pair_symbol}")
    
    async def unsubscribe_trade(self, pair_symbol: str):
        """Unsubscribe from trade channel."""
        unsub_msg = [
            151,
            {
                "type": 151,
                "channel": "trade",
                "event": pair_symbol,
                "join": False,
            },
        ]
        
        await self._send_ws_message(unsub_msg)
        
        # Remove from subscriptions
        self.subscriptions = [
            s for s in self.subscriptions
            if not (s[1].get("channel") == "trade" and s[1].get("event") == pair_symbol)
        ]
        
        logger.info(f"Unsubscribed from trade channel: {pair_symbol}")
    
    async def unsubscribe_orderbook(self, pair_symbol: str):
        """Unsubscribe from orderbook channels."""
        for channel in ["orderbook", "obdiff"]:
            unsub_msg = [
                151,
                {
                    "type": 151,
                    "channel": channel,
                    "event": pair_symbol,
                    "join": False,
                },
            ]
            await self._send_ws_message(unsub_msg)
        
        # Remove from subscriptions
        self.subscriptions = [
            s for s in self.subscriptions
            if not (
                s[1].get("channel") in ["orderbook", "obdiff"]
                and s[1].get("event") == pair_symbol
            )
        ]
        
        # Clear orderbook state
        if pair_symbol in self.orderbooks:
            del self.orderbooks[pair_symbol]
        
        logger.info(f"Unsubscribed from orderbook channels: {pair_symbol}")
    
    async def unsubscribe_ticker(self, pair_symbol: str):
        """Unsubscribe from ticker channel."""
        unsub_msg = [
            151,
            {
                "type": 151,
                "channel": "ticker",
                "event": pair_symbol,
                "join": False,
            },
        ]
        
        await self._send_ws_message(unsub_msg)
        
        # Remove from subscriptions
        self.subscriptions = [
            s for s in self.subscriptions
            if not (
                s[1].get("channel") == "ticker" and s[1].get("event") == pair_symbol
            )
        ]
        
        logger.info(f"Unsubscribed from ticker channel: {pair_symbol}")
    
    # =========================================================================
    # ORDERBOOK HELPERS
    # =========================================================================
    
    def get_best_bid_ask(
        self, pair: str
    ) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """
        Get best bid and ask from local orderbook.
        
        Args:
            pair: Trading pair symbol (e.g., "BTCTRY")
        
        Returns:
            ((best_bid_price, best_bid_qty), (best_ask_price, best_ask_qty))
            or None if orderbook not available
        """
        if pair not in self.orderbooks:
            return None
        
        ob = self.orderbooks[pair]
        
        if not ob["bids"] or not ob["asks"]:
            return None
        
        best_bid = ob["bids"][0]
        best_ask = ob["asks"][0]
        
        return (best_bid, best_ask)
    
    # =========================================================================
    # REST - AUTHENTICATION
    # =========================================================================
    
    def _sign_rest(self, path: str, body: str, timestamp: int) -> str:
        """
        Sign REST request using HMAC-SHA256.
        
        BtcTurk REST Authentication:
        - message = publicKey + timestamp (nonce in milliseconds)
        - signature = HMAC-SHA256(base64_decode(privateKey), message)
        - result = base64_encode(signature)
        
        Note: Path and body are NOT included in the signature!
        
        Args:
            path: Request path (not used in signature, kept for compatibility)
            body: Request body (not used in signature, kept for compatibility)
            timestamp: Timestamp in milliseconds (used as nonce)
        
        Returns:
            Base64-encoded signature
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials not provided")
        
        # Build message: ONLY publicKey + timestamp (no path, no body!)
        message = f"{self.api_key}{timestamp}"
        
        # Decode secret from base64
        secret_bytes = base64.b64decode(self.api_secret)
        
        # Create HMAC signature
        signature_bytes = hmac.new(
            secret_bytes,
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        
        # Encode signature to base64
        signature = base64.b64encode(signature_bytes).decode("utf-8")
        
        return signature
    
    async def _rest_get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        """Execute REST GET request."""
        session = await self._get_session()
        url = f"{self.rest_base_url}{path}"
        
        headers = {}
        
        if private:
            timestamp = int(time.time() * 1000)
            signature = self._sign_rest(path, "", timestamp)
            
            headers.update({
                "X-PCK": self.api_key,
                "X-Stamp": str(timestamp),
                "X-Signature": signature,
                "Content-Type": "application/json",
            })
        
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"REST GET error {resp.status}: {text}")
                raise Exception(f"REST GET failed: {resp.status} - {text}")
            
            return await resp.json()
    
    async def _rest_post(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        """Execute REST POST request."""
        session = await self._get_session()
        url = f"{self.rest_base_url}{path}"
        
        headers = {"Content-Type": "application/json"}
        body_str = json.dumps(json_body) if json_body else ""
        
        if private:
            timestamp = int(time.time() * 1000)
            signature = self._sign_rest(path, body_str, timestamp)
            
            headers.update({
                "X-PCK": self.api_key,
                "X-Stamp": str(timestamp),
                "X-Signature": signature,
            })
        
        async with session.post(url, data=body_str, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"REST POST error {resp.status}: {text}")
                raise Exception(f"REST POST failed: {resp.status} - {text}")
            
            return await resp.json()
    
    async def _rest_delete(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        """Execute REST DELETE request."""
        session = await self._get_session()
        url = f"{self.rest_base_url}{path}"
        
        headers = {"Content-Type": "application/json"}
        body_str = json.dumps(json_body) if json_body else ""
        
        if private:
            timestamp = int(time.time() * 1000)
            signature = self._sign_rest(path, body_str, timestamp)
            
            headers.update({
                "X-PCK": self.api_key,
                "X-Stamp": str(timestamp),
                "X-Signature": signature,
            })
        
        async with session.delete(url, data=body_str, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"REST DELETE error {resp.status}: {text}")
                raise Exception(f"REST DELETE failed: {resp.status} - {text}")
            
            return await resp.json()
    
    # =========================================================================
    # REST - PUBLIC ENDPOINTS
    # =========================================================================
    
    async def get_ticker(self, pair_symbol: str) -> Dict[str, Any]:
        """
        Get ticker for a pair.
        
        Args:
            pair_symbol: Trading pair (e.g., "BTCTRY")
        
        Returns:
            Ticker data
        """
        return await self._rest_get(
            "/api/v2/ticker",
            params={"pairSymbol": pair_symbol},
        )
    
    async def get_orderbook(self, pair_symbol: str) -> Dict[str, Any]:
        """
        Get orderbook for a pair.
        
        Args:
            pair_symbol: Trading pair (e.g., "BTCTRY")
        
        Returns:
            Orderbook data with bids and asks
        """
        return await self._rest_get(
            "/api/v2/orderbook",
            params={"pairSymbol": pair_symbol},
        )
    
    async def get_trades(
        self, pair_symbol: str, last: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent trades for a pair.
        
        Args:
            pair_symbol: Trading pair (e.g., "BTCTRY")
            last: Number of trades to return (optional)
        
        Returns:
            List of recent trades
        """
        params = {"pairSymbol": pair_symbol}
        if last:
            params["last"] = last
        
        return await self._rest_get("/api/v2/trades", params=params)
    
    # =========================================================================
    # REST - PRIVATE ENDPOINTS
    # =========================================================================
    
    async def get_balances(self) -> List[Dict[str, Any]]:
        """
        Get account balances.
        
        Returns:
            List of balances for all assets
        """
        return await self._rest_get("/api/v1/users/balances", private=True)
    
    async def get_open_orders(
        self, pair_symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get open orders.
        
        Args:
            pair_symbol: Optional pair to filter by
        
        Returns:
            List of open orders
        """
        params = {}
        if pair_symbol:
            params["pairSymbol"] = pair_symbol
        
        return await self._rest_get("/api/v1/openOrders", params=params, private=True)
    
    async def get_order(self, order_id: int) -> Dict[str, Any]:
        """
        Get order details by ID.
        
        Args:
            order_id: Order ID
        
        Returns:
            Order details
        """
        return await self._rest_get(f"/api/v1/order?id={order_id}", private=True)
    
    async def create_order(
        self,
        pair_symbol: str,
        side: str,
        price: float,
        quantity: float,
        order_type: str = "limit",
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new order.
        
        Args:
            pair_symbol: Trading pair (e.g., "BTCTRY")
            side: "buy" or "sell"
            price: Order price (ignored for market orders)
            quantity: For LIMIT orders: crypto amount (e.g., 0.0001 BTC)
                     For MARKET BUY: quote currency amount (e.g., 500 TRY)
                     For MARKET SELL: crypto amount (e.g., 0.0001 BTC)
            order_type: "limit", "market", "stoplimit", or "stopmarket"
            stop_price: Stop price (only for stop orders)
            client_order_id: Optional client-side order ID
        
        Returns:
            Order creation result
        """
        # BtcTurk API requires string values for orderMethod and orderType
        order_method = order_type.lower()  # "limit", "market", "stoplimit", "stopmarket"
        order_type_str = side.lower()  # "buy" or "sell"
        
        # Format quantity as string to avoid scientific notation
        # For market BUY orders, quantity is in quote currency (TRY/USDT)
        # For market SELL and all limit orders, quantity is in base currency (BTC/crypto)
        if isinstance(quantity, float):
            # For market BUY with quote currency, we typically want integer or 2 decimals
            if order_method == "market" and order_type_str == "buy":
                # Quote currency amount (TRY) - typically integer or 2 decimals
                quantity_str = f"{quantity:.2f}".rstrip('0').rstrip('.')
            else:
                # Crypto amount - up to 8 decimals
                quantity_str = f"{quantity:.8f}".rstrip('0').rstrip('.')
        else:
            quantity_str = str(quantity)
        
        # Format price - if it's a whole number, keep it as integer string
        if price and isinstance(price, float) and price == int(price):
            price_str = str(int(price))
        elif price:
            price_str = str(price)
        else:
            price_str = "0"
        
        body = {
            "pairSymbol": pair_symbol,
            "orderType": order_type_str,
            "orderMethod": order_method,
            "price": price_str,
            "quantity": quantity_str,
        }
        
        if stop_price is not None:
            if isinstance(stop_price, float) and stop_price == int(stop_price):
                body["stopPrice"] = str(int(stop_price))
            else:
                body["stopPrice"] = str(stop_price)
        
        if client_order_id:
            body["newOrderClientId"] = client_order_id
        
        return await self._rest_post("/api/v1/order", json_body=body, private=True)
    
    async def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            Cancellation result
        """
        # BtcTurk requires id as query parameter, not in body
        path = f"/api/v1/order?id={order_id}"
        return await self._rest_delete(path, private=True)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def main():
    """Example usage of BtcturkClient."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Initialize client (credentials loaded from .env automatically)
    client = BtcturkClient()
    
    # Check if credentials are loaded
    if not client.ws_public_key or not client.ws_private_key:
        logger.error("WebSocket credentials not found in .env file!")
        logger.error("Please set BTC_TURK_Public_Key and BTC_TURK_Private_Key")
        return
    
    try:
        # Test REST API
        logger.info("=== Testing REST API ===")
        
        ticker = await client.get_ticker("BTCTRY")
        logger.info(f"Ticker: {ticker}")
        
        orderbook = await client.get_orderbook("BTCTRY")
        logger.info(f"Orderbook bids: {len(orderbook.get('bids', []))}")
        
        # Test WebSocket
        logger.info("=== Testing WebSocket ===")
        
        def on_message(msg):
            """Callback for all WebSocket messages."""
            logger.debug(f"Received: {msg}")
        
        # Start WebSocket connection in background
        ws_task = asyncio.create_task(client.connect(on_message))
        
        # Wait for connection
        await asyncio.sleep(2)
        
        # Subscribe to channels
        await client.subscribe_ticker("BTCTRY")
        await client.subscribe_trade("BTCTRY")
        await client.subscribe_orderbook("BTCTRY")
        
        # Monitor for 30 seconds
        await asyncio.sleep(30)
        
        # Check local orderbook
        best = client.get_best_bid_ask("BTCTRY")
        if best:
            (bid_price, bid_qty), (ask_price, ask_qty) = best
            logger.info(
                f"Best bid: {bid_price} ({bid_qty}), "
                f"Best ask: {ask_price} ({ask_qty})"
            )
        
        # Disconnect
        await client.disconnect()
        await ws_task
    
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
