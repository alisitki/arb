"""
Test BtcTurk WebSocket Authentication with NONCE (sabit sayı)
Örnek koddan farklı olarak nonce kullanıyor
"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
import os
import websockets
from dotenv import load_dotenv

load_dotenv()

WS_PUBLIC = os.getenv("BTC_TURK_WS_Public_Key")
WS_PRIVATE = os.getenv("BTC_TURK_WS_Private_Key")

print(f"WS Public Key: {WS_PUBLIC[:20]}...")

async def test():
    ws = await websockets.connect("wss://ws-feed-pro.btcturk.com/")
    print("✓ Connected!")
    
    # KRITIK: nonce sabit bir sayı (örnek kodda 3000)
    nonce = 3000
    
    print(f"\nnonce: {nonce}")
    
    # baseString = publicKey + nonce (STRING olarak!)
    baseString = f"{WS_PUBLIC}{nonce}".encode("utf-8")
    print(f"baseString: {baseString[:50]}...")
    
    # Signature oluştur
    signature = hmac.new(
        base64.b64decode(WS_PRIVATE), 
        baseString, 
        hashlib.sha256
    ).digest()
    print(f"signature (bytes): {signature[:20]}...")
    
    signature = base64.b64encode(signature)
    print(f"signature (base64): {signature[:30]}...")
    
    timestamp = round(time.time() * 1000)
    print(f"timestamp: {timestamp}")
    
    hmacMessageObject = [
        114,
        {
            "nonce": nonce,
            "publicKey": WS_PUBLIC,
            "signature": signature.decode("utf-8"),
            "timestamp": timestamp,
            "type": 114,
        },
    ]
    
    print("\n✉️  Sending auth message...")
    await ws.send(json.dumps(hmacMessageObject))
    
    # Wait for response
    for i in range(3):
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(response)
            print(f"\n📩 Response {i+1}: {msg}")
            
            if isinstance(msg, list) and len(msg) >= 2 and msg[0] == 114:
                payload = msg[1]
                if payload.get('ok') or payload.get('OK'):
                    print("\n✅✅✅ BAŞARILI! Authentication SUCCESS!")
                    print("🎉 Private channels artık aktif!")
                    return True
                else:
                    print(f"\n❌ Failed: {payload.get('message')}")
                    return False
        except asyncio.TimeoutError:
            print(f"⏳ Waiting for response...")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    return False

if __name__ == "__main__":
    success = asyncio.run(test())
    print(f"\n{'='*60}")
    print(f"Final Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
    print(f"{'='*60}")
