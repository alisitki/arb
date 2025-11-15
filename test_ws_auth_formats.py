"""
Test different WebSocket authentication formats for BtcTurk
Try various combinations to find the correct format
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from dotenv import load_dotenv
import websockets

load_dotenv()

PUBLIC_KEY = os.getenv("BTC_TURK_Public_Key")
PRIVATE_KEY = os.getenv("BTC_TURK_Private_Key")
WS_URL = "wss://ws-feed-pro.btcturk.com/"


async def test_auth_format(name, login_message):
    """Test a specific authentication format."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    
    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            print("✓ Connected to WebSocket")
            
            # Send login message
            await ws.send(json.dumps(login_message))
            print(f"✓ Sent: {json.dumps(login_message, indent=2)}")
            
            # Wait for response (with timeout)
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = json.loads(response)
                print(f"✓ Response: {json.dumps(msg, indent=2)}")
                
                if isinstance(msg, list) and len(msg) >= 2:
                    code = msg[0]
                    payload = msg[1]
                    
                    if code == 114:
                        ok = payload.get('ok') or payload.get('OK')
                        if ok is True or ok == 1:
                            print("✅ SUCCESS! Authentication worked!")
                            return True
                        else:
                            print(f"❌ FAILED: {payload.get('message', 'Unknown error')}")
                            return False
                
            except asyncio.TimeoutError:
                print("❌ TIMEOUT: No response from server")
                return False
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


async def main():
    print(f"Public Key: {PUBLIC_KEY[:20]}...")
    print(f"Private Key (base64): {PRIVATE_KEY[:20]}...")
    
    timestamp = int(time.time() * 1000)
    private_key_bytes = base64.b64decode(PRIVATE_KEY)
    
    # Format 1: Current implementation (publicKey + timestamp)
    base_string_1 = f"{PUBLIC_KEY}{timestamp}"
    signature_1 = base64.b64encode(
        hmac.new(private_key_bytes, base_string_1.encode(), hashlib.sha256).digest()
    ).decode()
    
    await test_auth_format(
        "Format 1: [114, {type, publicKey, timestamp, signature}]",
        [114, {
            "type": 114,
            "publicKey": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_1
        }]
    )
    
    # Format 2: Without type field
    await test_auth_format(
        "Format 2: [114, {publicKey, timestamp, signature}]",
        [114, {
            "publicKey": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_1
        }]
    )
    
    # Format 3: With nonce field
    await test_auth_format(
        "Format 3: [114, {type, publicKey, nonce, timestamp, signature}]",
        [114, {
            "type": 114,
            "publicKey": PUBLIC_KEY,
            "nonce": timestamp,
            "timestamp": timestamp,
            "signature": signature_1
        }]
    )
    
    # Format 4: Just the object (not in array)
    await test_auth_format(
        "Format 4: {type, publicKey, timestamp, signature}",
        {
            "type": 114,
            "publicKey": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_1
        }
    )
    
    # Format 5: Different signature (include "114" in message)
    base_string_5 = f"114{PUBLIC_KEY}{timestamp}"
    signature_5 = base64.b64encode(
        hmac.new(private_key_bytes, base_string_5.encode(), hashlib.sha256).digest()
    ).decode()
    
    await test_auth_format(
        "Format 5: [114, ...] with '114' in signature base",
        [114, {
            "type": 114,
            "publicKey": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_5
        }]
    )
    
    # Format 6: Lowercase fields
    await test_auth_format(
        "Format 6: [114, ...] with lowercase 'publickey'",
        [114, {
            "type": 114,
            "publickey": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_1
        }]
    )
    
    # Format 7: Using 'key' instead of 'publicKey'
    await test_auth_format(
        "Format 7: [114, ...] with 'key' instead of 'publicKey'",
        [114, {
            "type": 114,
            "key": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_1
        }]
    )
    
    # Format 8: Signature from just timestamp (no publicKey)
    base_string_8 = f"{timestamp}"
    signature_8 = base64.b64encode(
        hmac.new(private_key_bytes, base_string_8.encode(), hashlib.sha256).digest()
    ).decode()
    
    await test_auth_format(
        "Format 8: signature from timestamp only",
        [114, {
            "type": 114,
            "publicKey": PUBLIC_KEY,
            "timestamp": timestamp,
            "signature": signature_8
        }]
    )
    
    print(f"\n{'='*60}")
    print("All tests completed!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
