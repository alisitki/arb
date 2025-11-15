"""
Test market order WITHOUT price field
"""
import asyncio
import logging
from exchange_clients.btcturk_client import BtcturkClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_market_no_price():
    client = BtcturkClient()
    
    logger.info("=" * 80)
    logger.info("Testing MARKET order WITHOUT 'price' field:")
    logger.info("=" * 80)
    
    test_cases = [
        {
            "name": "NO price field at all",
            "body": {
                "pairSymbol": "BTCTRY",
                "orderType": "buy",
                "orderMethod": "market",
                "quantity": "0.0001",
            }
        },
        {
            "name": "price = null",
            "body": {
                "pairSymbol": "BTCTRY",
                "orderType": "buy",
                "orderMethod": "market",
                "price": None,
                "quantity": "0.0001",
            }
        },
        {
            "name": "Empty string price",
            "body": {
                "pairSymbol": "BTCTRY",
                "orderType": "buy",
                "orderMethod": "market",
                "price": "",
                "quantity": "0.0001",
            }
        },
    ]
    
    for test in test_cases:
        logger.info(f"\n{test['name']}:")
        logger.info(f"Body: {test['body']}")
        
        try:
            result = await client._rest_post("/api/v1/order", json_body=test['body'], private=True)
            logger.info(f"✅ SUCCESS! {test['name']} worked!")
            logger.info(f"Result: {result}")
            
            # Cancel if successful
            if result.get("success") and result.get("data", {}).get("id"):
                order_id = result["data"]["id"]
                logger.info(f"Canceling test order {order_id}...")
                await client.cancel_order(order_id)
                
            break
            
        except Exception as e:
            logger.error(f"❌ {e}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_market_no_price())
