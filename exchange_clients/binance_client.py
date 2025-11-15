import asyncio
import json
import time
import hmac
import hashlib
import aiohttp
import websockets
from typing import Callable, Optional, Dict, Any



class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

        # WS URLs
        self.stream_url = "wss://stream.binance.com:9443/stream?streams="
        self.rest_url = "https://api.binance.com"

        # Async objects
        self.ws = None
        self.session = aiohttp.ClientSession()

        # Reconnect & state
        self.running = False
        self.streams = []
        self.listen_key = None   # userDataStream
        
        # Heartbeat / metrics
        self.last_msg_ts = time.time()
        self.heartbeat_timeout = 45
        self.latency_rtt = 0  # Latency in milliseconds

        # Orderbook
        self.orderbook = {"bids": [], "asks": []}

        # Rate limit
        self.bucket = 1200  # 1200 weight / 1 dk
        self.bucket_reset = time.time() + 60
        self.lock = asyncio.Lock()


    #############################################
    # ----------- RATE LIMIT BUCKET -------------
    #############################################
    async def _rate_limit(self, weight: int):
        async with self.lock:
            now = time.time()
            if now >= self.bucket_reset:
                self.bucket = 1200
                self.bucket_reset = now + 60

            if self.bucket < weight:
                await asyncio.sleep(self.bucket_reset - now)

            self.bucket -= weight


    #############################################
    # --------------- SIGNATURE -----------------
    #############################################
    def _sign(self, params: Dict[str, Any]):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()
        return query + "&signature=" + signature


    #############################################
    # ----------------- REST --------------------
    #############################################
    async def rest_get(self, path: str, params=None, weight=1, private=False):
        await self._rate_limit(weight)
        url = f"{self.rest_url}{path}"

        headers = {}
        if private:
            params["timestamp"] = int(time.time() * 1000)
            query = self._sign(params)
            url = f"{url}?{query}"
            headers["X-MBX-APIKEY"] = self.api_key
            params = None

        async with self.session.get(url, params=params, headers=headers) as r:
            return await r.json()

    async def rest_post(self, path: str, params=None, weight=1, signed=True):
        await self._rate_limit(weight)
        url = f"{self.rest_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key}

        if signed:
            if params is None:
                params = {}
            params["timestamp"] = int(time.time() * 1000)
            query = self._sign(params)
            url = f"{url}?{query}"

        async with self.session.post(url, headers=headers) as r:
            return await r.json()


    #############################################
    # ----------- USER DATA STREAM --------------
    #############################################
    async def start_user_stream(self):
        """Order fill eventleri almak için listenKey al."""
        data = await self.rest_post("/api/v3/userDataStream", params={}, weight=1, signed=False)
        print("DEBUG: UserDataStream response:", data)
        
        if "listenKey" not in data:
            print(f"ERROR: listenKey not found in response. Full response: {data}")
            if "code" in data:
                print(f"API Error Code: {data.get('code')}, Message: {data.get('msg')}")
            return
        
        self.listen_key = data["listenKey"]
        self.streams.append(f"{self.listen_key}")
        print("UserData listenKey:", self.listen_key)


    #############################################
    # --------------- ORDERBOOK -----------------
    #############################################
    async def load_orderbook_snapshot(self, symbol="BTCUSDT"):
        """REST + WS delta merge için snapshot."""
        data = await self.rest_get("/api/v3/depth", {"symbol": symbol, "limit": 100}, weight=50)
        self.orderbook["bids"] = [(float(p), float(q)) for p, q in data["bids"]]
        self.orderbook["asks"] = [(float(p), float(q)) for p, q in data["asks"]]

    def apply_orderbook_delta(self, update):
        """WS depth update → orderbook merge."""
        for bid in update.get("b", []):
            price, qty = float(bid[0]), float(bid[1])
            self._update_level(self.orderbook["bids"], price, qty, reverse=True)

        for ask in update.get("a", []):
            price, qty = float(ask[0]), float(ask[1])
            self._update_level(self.orderbook["asks"], price, qty, reverse=False)

    @staticmethod
    def _update_level(levels, price, qty, reverse):
        for i, (p, _) in enumerate(levels):
            if p == price:
                if qty == 0:
                    del levels[i]
                else:
                    levels[i] = (price, qty)
                return
        if qty > 0:
            levels.append((price, qty))
        levels.sort(key=lambda x: x[0], reverse=reverse)


    #############################################
    # ----------------- WEBSOCKET ---------------
    #############################################
    async def connect(self, on_message: Callable):
        """Multi-stream WebSocket."""
        self.running = True

        while self.running:
            try:
                url = self.stream_url + "/".join(self.streams)
                print("Connecting:", url)

                async with websockets.connect(url, ping_interval=None) as ws:
                    self.ws = ws
                    self.last_msg_ts = time.time()

                    heartbeat = asyncio.create_task(self._heartbeat())

                    async for msg in ws:
                        ts = time.time()
                        data = json.loads(msg)

                        self.last_msg_ts = ts
                        
                        # Calculate latency from event timestamp
                        self._calculate_latency(data, ts)
                        
                        await on_message(data)

            except Exception as e:
                print("WS ERROR:", e)
                await asyncio.sleep(2)
                print("Reconnecting...")


    def _calculate_latency(self, data: dict, receive_time: float):
        """
        Calculate latency from WebSocket event timestamp.
        
        Args:
            data: WebSocket message data
            receive_time: Time when message was received (seconds)
        """
        try:
            # Multi-stream format: {"stream": "...", "data": {...}}
            if "stream" in data and "data" in data:
                payload = data["data"]
                
                # Extract event timestamp (E field) - in milliseconds
                event_timestamp_ms = payload.get("E")
                
                if event_timestamp_ms:
                    # Convert receive time to milliseconds
                    receive_time_ms = receive_time * 1000
                    
                    # Calculate latency: now - event_timestamp
                    self.latency_rtt = receive_time_ms - event_timestamp_ms
                    
        except Exception as e:
            # Silently ignore latency calculation errors
            pass


    async def _heartbeat(self):
        while self.running:
            await asyncio.sleep(5)
            if time.time() - self.last_msg_ts > self.heartbeat_timeout:
                print("Heartbeat timeout! Reconnecting...")
                await self._reconnect()


    async def _reconnect(self):
        try:
            await self.ws.close()
        except:
            pass


    #############################################
    # ----------------- ORDERS ------------------
    #############################################
    async def create_order(self, symbol, side, order_type, quantity, price=None):
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }
        if price:
            params["price"] = price
            params["timeInForce"] = "GTC"

        return await self.rest_post("/api/v3/order", params=params, weight=10)


    #############################################
    # ---------------- DISCONNECT --------------
    #############################################
    async def disconnect(self):
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                print(f"Warning: Error closing websocket: {e}")
        try:
            await self.session.close()
        except Exception as e:
            print(f"Warning: Error closing session: {e}")
