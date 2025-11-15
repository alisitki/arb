"""
Test if BtcTurk market orders require 'total' instead of 'quantity'
"""
import asyncio
import logging
from exchange_clients.btcturk_client import BtcturkClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_market_with_total():
    client = BtcturkClient()
    
    # Get current price
    ticker = await client.get_ticker("BTCTRY")
    current_price = float(ticker['data'][0]['last'])
    logger.info(f"Current BTCTRY price: {current_price:,.2f}")
    
    logger.info("\n" + "=" * 80)
    logger.info("Testing MARKET order with 'total' parameter (TRY amount):")
    logger.info("=" * 80)
    
    # Try with 'total' instead of 'quantity'
    total_try = 500  # 500 TRY
    
    logger.info(f"\nTest Total: {total_try} TRY")
    logger.info(f"Expected BTC: ~{total_try / current_price:.8f}")
    
    try:
        body = {
            "pairSymbol": "BTCTRY",
            "orderType": "buy",
            "orderMethod": "market",
            "total": str(total_try),  # Using 'total' instead of 'quantity'
        }
        logger.info(f"Request body: {body}")
        
        result = await client._rest_post("/api/v1/order", json_body=body, private=True)
        logger.info(f"✅ SUCCESS! Order created: {result}")
        
        # If successful, this is the right format!
        if result.get("success"):
            logger.info("\n🎉 FOUND IT! Market orders need 'total' parameter, not 'quantity'!")
            
    except Exception as e:
        logger.error(f"❌ FAIL with 'total': {e}")
        
        # Also try with both quantity AND total
        logger.info("\nTrying with BOTH 'quantity' and 'total'...")
        try:
            body = {
                "pairSymbol": "BTCTRY",
                "orderType": "buy",
                "orderMethod": "market",
                "quantity": "0.0001",
                "total": str(total_try),
            }
            logger.info(f"Request body: {body}")
            
            result = await client._rest_post("/api/v1/order", json_body=body, private=True)
            logger.info(f"✅ SUCCESS! Order created: {result}")
            
        except Exception as e2:
            logger.error(f"❌ FAIL with both: {e2}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_market_with_total())
