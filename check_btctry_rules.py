"""
Quick test to check BTCTRY pair info and trading rules
"""
import asyncio
import aiohttp

async def check_pair_info():
    async with aiohttp.ClientSession() as session:
        # Get server exchange info
        async with session.get("https://api.btcturk.com/api/v2/server/exchangeinfo") as resp:
            data = await resp.json()
            
            # Find BTCTRY pair
            for symbol in data.get("data", {}).get("symbols", []):
                if symbol.get("name") == "BTCTRY":
                    print("BTCTRY Trading Rules:")
                    print(f"  Name: {symbol.get('name')}")
                    print(f"  Name Normalized: {symbol.get('nameNormalized')}")
                    print(f"  Status: {symbol.get('status')}")
                    print(f"  Numerator: {symbol.get('numerator')}")
                    print(f"  Denominator: {symbol.get('denominator')}")
                    print(f"  Numerator Scale: {symbol.get('numeratorScale')}")
                    print(f"  Denominator Scale: {symbol.get('denominatorScale')}")
                    print(f"  Has Fraction: {symbol.get('hasFraction')}")
                    print(f"  Filters:")
                    for filter_item in symbol.get("filters", []):
                        print(f"    {filter_item}")
                    break

asyncio.run(check_pair_info())
