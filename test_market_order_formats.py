"""
Test different market order formats to debug FAILED_INVALID_QUANTITY_SCALE
"""
import asyncio
import logging
from exchange_clients.btcturk_client import BtcturkClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_market_formats():
    client = BtcturkClient()
    
    # Get current price
    ticker = await client.get_ticker("BTCTRY")
    current_price = float(ticker['data'][0]['last'])
    logger.info(f"Current BTCTRY price: {current_price:,.2f}")
    
    # Test different quantity formats
    test_quantities = [
        0.0001,     # Original
        0.001,      # 10x larger
        0.0002,     # 2x original
        0.00015,    # 1.5x original
    ]
    
    logger.info("\n" + "=" * 80)
    logger.info("Testing different quantity formats for MARKET BUY order:")
    logger.info("=" * 80)
    
    for qty in test_quantities:
        # Format as string without scientific notation
        qty_str = f"{qty:.8f}".rstrip('0').rstrip('.')
        estimated_cost = qty * current_price
        
        logger.info(f"\nTest Quantity: {qty_str} BTC")
        logger.info(f"Estimated Cost: ~{estimated_cost:.2f} TRY")
        
        # Try creating order (DRY RUN - will fail but we'll see the error)
        try:
            body = {
                "pairSymbol": "BTCTRY",
                "orderType": "buy",
                "orderMethod": "market",
                "price": "0",
                "quantity": qty_str,
            }
            logger.info(f"Request body: {body}")
            
            result = await client._rest_post("/api/v1/order", json_body=body, private=True)
            logger.info(f"✅ SUCCESS! Order created: {result}")
            
            # If successful, cancel immediately
            if result.get("success") and result.get("data", {}).get("id"):
                order_id = result["data"]["id"]
                logger.info(f"Canceling test order {order_id}...")
                await client.cancel_order(order_id)
                logger.info(f"Order canceled")
            
            break  # Found working format
            
        except Exception as e:
            logger.error(f"❌ FAIL: {e}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_market_formats())
