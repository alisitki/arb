"""
Final test: Market BUY with ONLY total (no quantity)
"""
import asyncio
import logging
from exchange_clients.btcturk_client import BtcturkClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test():
    client = BtcturkClient()
    
    logger.info("=" * 80)
    logger.info("FINAL TEST: Market BUY with TOTAL only (no quantity, no price)")
    logger.info("=" * 80)
    
    body = {
        "pairSymbol": "BTCTRY",
        "orderType": "buy",
        "orderMethod": "market",
        "total": "500",  # 500 TRY - NO quantity, NO price
    }
    
    logger.info(f"Body: {body}")
    logger.info("⚠️  This will execute a REAL market order for 500 TRY!")
    logger.info("Waiting 2 seconds... (Ctrl+C to cancel)")
    await asyncio.sleep(2)
    
    try:
        result = await client._rest_post("/api/v1/order", json_body=body, private=True)
        logger.info(f"\n✅ SUCCESS!")
        logger.info(f"Result: {result}")
        logger.info(f"\n🎉 FOUND IT! Market BUY needs 'total' (TRY amount) instead of 'quantity'!")
        
    except Exception as e:
        logger.error(f"❌ {e}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(test())
