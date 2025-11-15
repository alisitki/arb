"""
Debug script to test BtcTurk authentication
"""
import asyncio
import base64
import hashlib
import hmac
import os
import time
import aiohttp
from dotenv import load_dotenv

load_dotenv()

async def test_auth():
    public_key = os.getenv("BTC_TURK_Public_Key")
    private_key = os.getenv("BTC_TURK_Private_Key")
    
    print(f"Public Key: {public_key}")
    print(f"Private Key: {private_key[:10]}... (truncated)")
    
    # Test REST API authentication
    path = "/api/v1/users/balances"
    timestamp = int(time.time() * 1000)
    
    # Build message: publicKey + timestamp + path + body
    message = f"{public_key}{timestamp}{path}"
    
    print(f"\nTimestamp: {timestamp}")
    print(f"Path: {path}")
    print(f"Message to sign: {message}")
    
    # Decode private key from base64
    try:
        private_key_bytes = base64.b64decode(private_key)
        print(f"Private key decoded successfully ({len(private_key_bytes)} bytes)")
    except Exception as e:
        print(f"Error decoding private key: {e}")
        return
    
    # Create HMAC signature
    signature_bytes = hmac.new(
        private_key_bytes,
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    
    # Encode signature to base64
    signature = base64.b64encode(signature_bytes).decode("utf-8")
    
    print(f"Signature: {signature}")
    
    # Make request
    url = f"https://api.btcturk.com{path}"
    headers = {
        "X-PCK": public_key,
        "X-Stamp": str(timestamp),
        "X-Signature": signature,
        "Content-Type": "application/json",
    }
    
    print(f"\nRequest URL: {url}")
    print(f"Headers: {headers}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"\nResponse Status: {resp.status}")
            text = await resp.text()
            print(f"Response Body: {text[:500]}")
            
            if resp.status == 401:
                print("\n❌ 401 Unauthorized - Authentication failed")
                print("Possible issues:")
                print("- Key pair might be for WebSocket only")
                print("- Key pair might be expired")
                print("- API permissions might not be enabled")
                print("- Signature algorithm might be incorrect")
            elif resp.status == 200:
                print("\n✅ Authentication successful!")

if __name__ == "__main__":
    asyncio.run(test_auth())
