"""
Test if market orders only work for SELL side
"""
import asyncio
import logging
from exchange_clients.btcturk_client import BtcturkClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_market_sell():
    client = BtcturkClient()
    
    # Check if we have BTC
    balances_resp = await client.get_balances()
    balances = balances_resp.get("data", []) if isinstance(balances_resp.get("data"), list) else []
    
    btc_balance = None
    for bal in balances:
        if bal.get("asset") == "BTC" or bal.get("assetName") == "BTC":
            free_str = bal.get("free", "0")
            if isinstance(free_str, str):
                free_str = free_str.replace(",", ".")
            btc_balance = float(free_str)
            break
    
    logger.info(f"BTC Balance: {btc_balance}")
    
    if btc_balance and btc_balance >= 0.0001:
        logger.info("\n✅ We have BTC! Testing MARKET SELL...")
        
        try:
            body = {
                "pairSymbol": "BTCTRY",
                "orderType": "sell",  # SELL instead of BUY
                "orderMethod": "market",
                "price": "0",
                "quantity": "0.0001",
            }
            logger.info(f"Body: {body}")
            
            result = await client._rest_post("/api/v1/order", json_body=body, private=True)
            logger.info(f"✅ SUCCESS! Market SELL worked!")
            logger.info(f"Result: {result}")
            
        except Exception as e:
            logger.error(f"❌ Market SELL also failed: {e}")
    else:
        logger.info("\n❌ No BTC balance to test SELL")
        logger.info("But let's try anyway to see the error...")
        
        try:
            body = {
                "pairSymbol": "BTCTRY",
                "orderType": "sell",
                "orderMethod": "market",
                "price": "0",
                "quantity": "0.0001",
            }
            logger.info(f"Body: {body}")
            
            result = await client._rest_post("/api/v1/order", json_body=body, private=True)
            logger.info(f"Result: {result}")
            
        except Exception as e:
            logger.error(f"Error: {e}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_market_sell())
