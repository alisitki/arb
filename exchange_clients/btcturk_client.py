import asyncio
import json
import time
import hmac
import hashlib
import base64
from typing import Optional, Callable
import websockets
import aiohttp


class BTCTurkClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws_url = "wss://ws-feed.btcturk.com"
        self.rest_url = "https://api.btcturk.com"
        self.ws = None
        self.running = False
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30
        self.reconnect_delay = 5
        
    async def connect(self, on_message: Callable):
        """WebSocket bağlantısı kur"""
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    self.last_heartbeat = time.time()
                    
                    # Heartbeat task başlat
                    heartbeat_task = asyncio.create_task(self._heartbeat())
                    
                    async for message in ws:
                        data = json.loads(message)
                        await on_message(data)
                        self.last_heartbeat = time.time()
                        
            except Exception as e:
                print(f"BTCTurk WS error: {e}")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
                    
    async def _heartbeat(self):
        """Heartbeat kontrolü"""
        while self.running and self.ws:
            await asyncio.sleep(self.heartbeat_interval)
            if time.time() - self.last_heartbeat > self.heartbeat_interval * 2:
                print("BTCTurk heartbeat timeout, reconnecting...")
                await self.ws.close()
                
    async def subscribe(self, channels: list):
        """Channel'lara abone ol"""
        if self.ws:
            for channel in channels:
                subscribe_msg = {
                    "type": "subscribe",
                    "channel": channel,
                    "event": channel,
                    "join": True
                }
                await self.ws.send(json.dumps(subscribe_msg))
            
    async def get_ticker(self, pair_symbol: str):
        """REST: Ticker bilgisi al"""
        url = f"{self.rest_url}/api/v2/ticker"
        params = {"pairSymbol": pair_symbol}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                return await resp.json()
                
    async def get_orderbook(self, pair_symbol: str):
        """REST: Orderbook al"""
        url = f"{self.rest_url}/api/v2/orderbook"
        params = {"pairSymbol": pair_symbol}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                return await resp.json()
                
    def _generate_signature(self, timestamp: int):
        """BTCTurk signature oluştur"""
        message = f"{self.api_key}{timestamp}"
        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message.encode(),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()
        
    async def create_order(self, pair_symbol: str, order_type: str, order_method: str,
                          quantity: float, price: Optional[float] = None):
        """REST: Emir oluştur"""
        url = f"{self.rest_url}/api/v1/order"
        timestamp = int(time.time() * 1000)
        
        payload = {
            "pairSymbol": pair_symbol,
            "orderType": order_type,  # buy, sell
            "orderMethod": order_method,  # limit, market
            "quantity": quantity,
            "timestamp": timestamp
        }
        
        if price:
            payload["price"] = price
            
        signature = self._generate_signature(timestamp)
        
        headers = {
            "X-PCK": self.api_key,
            "X-Stamp": str(timestamp),
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                return await resp.json()
                
    async def get_balance(self):
        """REST: Bakiye bilgisi"""
        url = f"{self.rest_url}/api/v1/users/balances"
        timestamp = int(time.time() * 1000)
        signature = self._generate_signature(timestamp)
        
        headers = {
            "X-PCK": self.api_key,
            "X-Stamp": str(timestamp),
            "X-Signature": signature
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                return await resp.json()
                
    async def disconnect(self):
        """Bağlantıyı kapat"""
        self.running = False
        if self.ws:
            await self.ws.close()
