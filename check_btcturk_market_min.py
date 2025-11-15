import asyncio
import aiohttp
import os
from dotenv import load_dotenv

async def check_market_minimums():
    """Check minimum values for market orders"""
    load_dotenv()
    
    async with aiohttp.ClientSession() as session:
        # Get exchange info
        async with session.get("https://api.btcturk.com/api/v2/server/exchangeinfo") as resp:
            data = await resp.json()
            
        # Find BTCTRY
        for symbol in data.get("data", {}).get("symbols", []):
            if symbol.get("name") == "BTCTRY":
                print("=" * 80)
                print("BTCTURK MARKET ORDER REQUIREMENTS FOR BTCTRY:")
                print("=" * 80)
                
                # All relevant fields
                print(f"Minimum Market Order Quantity: {symbol.get('minMarketOrderQuantity', 'N/A')}")
                print(f"Minimum Market Order Value (TRY): {symbol.get('minMarketOrderValue', 'N/A')}")
                print(f"Min Exchange Value: {symbol.get('minExchangeValue', 'N/A')}")
                print(f"Min Amount: {symbol.get('minAmount', 'N/A')}")
                print(f"Max Amount: {symbol.get('maxAmount', 'N/A')}")
                print(f"Max Total: {symbol.get('maxTotal', 'N/A')}")
                print(f"")
                print(f"Numerator Scale (BTC decimals): {symbol.get('numeratorScale', 'N/A')}")
                print(f"Denominator Scale (TRY decimals): {symbol.get('denominatorScale', 'N/A')}")
                print(f"Tick Size: {symbol.get('tickSize', 'N/A')}")
                print(f"")
                print(f"Status: {symbol.get('status', 'N/A')}")
                print(f"Order Methods: {symbol.get('orderMethods', 'N/A')}")
                print("=" * 80)
                
                # Calculate what 0.0001 BTC would cost at current price
                print("\nCurrent market check:")
                async with session.get("https://api.btcturk.com/api/v2/ticker") as ticker_resp:
                    tickers = await ticker_resp.json()
                    for ticker in tickers.get("data", []):
                        if ticker.get("pair") == "BTCTRY":
                            last_price = float(ticker.get("last", 0))
                            test_qty = 0.0001
                            test_value = test_qty * last_price
                            print(f"Last Price: {last_price:,.2f} TRY")
                            print(f"")
                            print(f"Test quantity: {test_qty} BTC")
                            print(f"Test value: {test_value:,.2f} TRY")
                            
                            min_market_qty = symbol.get('minMarketOrderQuantity')
                            min_market_val = symbol.get('minMarketOrderValue')
                            
                            if min_market_qty:
                                min_qty = float(min_market_qty)
                                print(f"")
                                print(f"❌ Min Market Qty: {min_qty} BTC (our {test_qty} is {'OK' if test_qty >= min_qty else 'TOO SMALL'})")
                            
                            if min_market_val:
                                min_val = float(min_market_val)
                                print(f"❌ Min Market Value: {min_val} TRY (our {test_value:.2f} is {'OK' if test_value >= min_val else 'TOO SMALL'})")
                break

if __name__ == "__main__":
    asyncio.run(check_market_minimums())
