import asyncio
from exchange_clients.binance_client import BinanceClient


async def main():
    # API key gerekmez public endpoint'ler için
    client = BinanceClient(api_key="", api_secret="")
    
    print("=== Binance Ticker Test ===")
    ticker = await client.get_ticker("BTCUSDT")
    print(f"BTC Price: {ticker}")
    
    print("\n=== Binance Orderbook Test ===")
    orderbook = await client.get_orderbook("BTCUSDT", limit=5)
    print(f"Top 5 Bids: {orderbook['bids'][:5]}")
    print(f"Top 5 Asks: {orderbook['asks'][:5]}")
    
    print("\n✅ Tüm testler başarılı!")


if __name__ == "__main__":
    asyncio.run(main())
