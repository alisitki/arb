"""
Test script for BtcturkClient
Tests REST API and WebSocket connectivity
"""

import asyncio
import logging
from exchange_clients.btcturk_client import BtcturkClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def test_rest_api(client: BtcturkClient):
    """Test REST API endpoints."""
    logger.info("=" * 60)
    logger.info("TESTING REST API")
    logger.info("=" * 60)
    
    try:
        # Test ticker
        ticker = await client.get_ticker("BTCTRY")
        logger.info(f"✓ Ticker retrieved: {ticker.get('data', {})}")
        
        # Test orderbook
        orderbook = await client.get_orderbook("BTCTRY")
        bids_count = len(orderbook.get('data', {}).get('bids', []))
        asks_count = len(orderbook.get('data', {}).get('asks', []))
        logger.info(f"✓ Orderbook retrieved: {bids_count} bids, {asks_count} asks")
        
        # Test trades
        trades = await client.get_trades("BTCTRY", last=5)
        logger.info(f"✓ Recent trades retrieved: {len(trades.get('data', []))} trades")
        
    except Exception as e:
        logger.error(f"✗ REST API test failed: {e}")
        raise


async def test_websocket(client: BtcturkClient):
    """Test WebSocket connectivity and data streaming."""
    logger.info("=" * 60)
    logger.info("TESTING WEBSOCKET")
    logger.info("=" * 60)
    
    message_count = 0
    
    def on_message(msg):
        """Callback for WebSocket messages."""
        nonlocal message_count
        message_count += 1
        
        if message_count <= 5:  # Log first 5 messages
            msg_type = msg[0] if isinstance(msg, list) else "unknown"
            logger.info(f"✓ Received message type: {msg_type}")
    
    try:
        # Start WebSocket connection
        ws_task = asyncio.create_task(client.connect(on_message))
        
        # Wait for connection
        await asyncio.sleep(2)
        logger.info("✓ WebSocket connected")
        
        # Subscribe to channels
        await client.subscribe_ticker("BTCTRY")
        logger.info("✓ Subscribed to ticker")
        
        await client.subscribe_trade("BTCTRY")
        logger.info("✓ Subscribed to trades")
        
        await client.subscribe_orderbook("BTCTRY")
        logger.info("✓ Subscribed to orderbook")
        
        # Monitor for 10 seconds
        logger.info("Monitoring messages for 10 seconds...")
        await asyncio.sleep(10)
        
        # Check local orderbook
        best = client.get_best_bid_ask("BTCTRY")
        if best:
            (bid_price, bid_qty), (ask_price, ask_qty) = best
            logger.info(
                f"✓ Best bid: {bid_price:,.2f} TRY ({bid_qty:.8f} BTC)"
            )
            logger.info(
                f"✓ Best ask: {ask_price:,.2f} TRY ({ask_qty:.8f} BTC)"
            )
            spread = ask_price - bid_price
            spread_pct = (spread / bid_price) * 100
            logger.info(f"✓ Spread: {spread:,.2f} TRY ({spread_pct:.4f}%)")
        else:
            logger.warning("⚠ Orderbook not yet available")
        
        logger.info(f"✓ Total messages received: {message_count}")
        
        # Disconnect
        await client.disconnect()
        await ws_task
        
    except Exception as e:
        logger.error(f"✗ WebSocket test failed: {e}")
        await client.disconnect()
        raise


async def main():
    """Run all tests."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger.info("🚀 Starting BtcTurk Client Tests")
    logger.info("")
    
    # Initialize client (credentials from .env)
    client = BtcturkClient()
    
    # Verify credentials
    if not client.ws_public_key or not client.ws_private_key:
        logger.error("❌ WebSocket credentials not found in .env file!")
        logger.error("Please set BTC_TURK_Public_Key and BTC_TURK_Private_Key")
        return
    
    logger.info(f"✓ WebSocket Public Key loaded: {client.ws_public_key[:20]}...")
    logger.info(f"✓ WebSocket Private Key loaded: ***{client.ws_private_key[-10:]}")
    logger.info("")
    
    try:
        # Test REST API
        await test_rest_api(client)
        logger.info("")
        
        # Test WebSocket
        await test_websocket(client)
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("")
        logger.error("=" * 60)
        logger.error(f"❌ TESTS FAILED: {e}")
        logger.error("=" * 60)
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
