#!/usr/bin/env python3
"""
Test script to monitor BTCTurk trade messages
"""

import asyncio
import json
import websockets
import time

async def test_btcturk_trades():
    """Connect to BTCTurk and monitor all messages"""
    ws_url = "wss://ws-feed-pro.btcturk.com/"
    
    print(f"Connecting to {ws_url}")
    async with websockets.connect(ws_url, ping_interval=None) as ws:
        print("✓ Connected")
        
        # Subscribe to USDT/TRY trade channel
        subscribe_msg = [151, {"channel": "trade", "event": "USDTTRY", "join": True}]
        await ws.send(json.dumps(subscribe_msg))
        print("✓ Sent trade subscription for USDTTRY")
        
        # Also subscribe to ticker for comparison
        ticker_msg = [151, {"channel": "ticker", "event": "USDTTRY", "join": True}]
        await ws.send(json.dumps(ticker_msg))
        print("✓ Sent ticker subscription for USDTTRY")
        
        print("\nWaiting for messages (30 seconds)...")
        print("-" * 80)
        
        start_time = time.time()
        message_count = {}
        
        while time.time() - start_time < 30:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                
                if isinstance(msg, list) and len(msg) >= 2:
                    code = msg[0]
                    payload = msg[1]
                    
                    # Count messages by type
                    message_count[code] = message_count.get(code, 0) + 1
                    
                    # Show interesting messages
                    if code == 422:  # Trade
                        print(f"[TRADE 422] {payload}")
                    elif code == 421:  # Trade list
                        print(f"[TRADE LIST 421] {len(payload.get('items', []))} trades")
                    elif code == 401 or code == 402:  # Ticker
                        print(f"[TICKER {code}] PS={payload.get('PS')}, Last={payload.get('L')}")
                    elif code == 151:  # Subscribe result
                        print(f"[SUBSCRIBE RESULT 151] {payload}")
                    else:
                        print(f"[CODE {code}] {payload}")
            
            except asyncio.TimeoutError:
                continue
        
        print("-" * 80)
        print("\nMessage count summary:")
        for code, count in sorted(message_count.items()):
            print(f"  Code {code}: {count} messages")

if __name__ == "__main__":
    asyncio.run(test_btcturk_trades())
