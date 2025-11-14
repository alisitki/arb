import asyncio
import json
import time
import hmac
import hashlib
from typing import Optional, Callable
import websockets
import aiohttp


class ParibuClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws_url = "wss://stream.paribu.com/ws"
        self.rest_url = "https://api.paribu.com"
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
                print(f"Paribu WS error: {e}")
                if self.running:
                    await asyncio.sleep(self.reconnect_delay)
                    
    async def _heartbeat(self):
        """Heartbeat kontrolü"""
        while self.running and self.ws:
            await asyncio.sleep(self.heartbeat_interval)
            if time.time() - self.last_heartbeat > self.heartbeat_interval * 2:
                print("Paribu heartbeat timeout, reconnecting...")
                await self.ws.close()
                
    async def subscribe(self, channels: list):
        """Channel'lara abone ol"""
        if self.ws:
            subscribe_msg = {
                "type": "subscribe",
                "channels": channels,
                "timestamp": int(time.time() * 1000)
            }
            await self.ws.send(json.dumps(subscribe_msg))
            
    async def get_ticker(self, pair: str):
        """REST: Ticker bilgisi al"""
        url = f"{self.rest_url}/v1/ticker/{pair}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.json()
                
    async def get_orderbook(self, pair: str):
        """REST: Orderbook al"""
        url = f"{self.rest_url}/v1/orderbook/{pair}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.json()
                
    async def create_order(self, pair: str, side: str, order_type: str,
                          quantity: float, price: Optional[float] = None):
        """REST: Emir oluştur"""
        url = f"{self.rest_url}/v1/order"
        timestamp = int(time.time() * 1000)
        
        payload = {
            "pair": pair,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "timestamp": timestamp
        }
        
        if price:
            payload["price"] = price
            
        # Signature oluştur
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.api_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "X-API-KEY": self.api_key,
            "X-SIGNATURE": signature,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                return await resp.json()
                
    async def get_balance(self):
        """REST: Bakiye bilgisi"""
        url = f"{self.rest_url}/v1/balance"
        timestamp = int(time.time() * 1000)
        
        payload = {"timestamp": timestamp}
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.api_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "X-API-KEY": self.api_key,
            "X-SIGNATURE": signature
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                return await resp.json()
                
    async def disconnect(self):
        """Bağlantıyı kapat"""
        self.running = False
        if self.ws:
            await self.ws.close()
