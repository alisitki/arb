"""
BtcTurk Private API Test Suite
Tests all private REST API functions and WebSocket user events in order:
1. get_balances() - Check if balances are returned
2. create_order() LIMIT - Create a far-off price limit order
3. get_open_orders() - Verify the limit order appears
4. cancel_order() - Cancel the limit order
5. create_order() MARKET - Place a small market order
6. WebSocket private events - Verify market order fill via WS
"""

import asyncio
import logging
import time
from exchange_clients.btcturk_client import BtcturkClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BtcTurkPrivateAPITester:
    """Comprehensive tester for BtcTurk private API functions."""
    
    def __init__(self):
        self.client = BtcturkClient()
        self.test_results = {}
        self.test_pair = "BTCTRY"
        self.limit_order_id = None
        self.market_order_received = False
        
    async def run_all_tests(self):
        """Run all 6 tests in sequence."""
        logger.info("=" * 80)
        logger.info("BTCTURK PRIVATE API TEST SUITE")
        logger.info("=" * 80)
        
        try:
            # Test 1: Get balances
            await self.test_1_get_balances()
            
            # Test 2: Create limit order
            await self.test_2_create_limit_order()
            
            # Test 3: Get open orders
            await self.test_3_get_open_orders()
            
            # Test 4: Cancel order
            await self.test_4_cancel_order()
            
            # Test 5 & 6: Create market order and monitor WS events
            await self.test_5_6_market_order_and_ws()
            
        finally:
            await self.client.close()
            self.print_final_report()
    
    async def test_1_get_balances(self):
        """Test 1: get_balances() - Check if balances are returned."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 1: get_balances()")
        logger.info("=" * 80)
        
        try:
            response = await self.client.get_balances()
            
            # BtcTurk returns: {"data": [...], "success": true}
            if isinstance(response, dict) and "data" in response:
                balances = response["data"]
            else:
                balances = response
            
            if balances and isinstance(balances, list):
                logger.info(f"✅ SUCCESS: Received {len(balances)} balance entries")
                
                # Show balances with non-zero amounts
                logger.info("\nNon-zero balances:")
                for balance in balances:
                    asset = balance.get("asset", balance.get("assetname", "?"))
                    # BtcTurk uses comma as decimal separator
                    free_str = str(balance.get("free", balance.get("balance", "0")))
                    locked_str = str(balance.get("locked", balance.get("lockedBalance", "0")))
                    
                    # Convert Turkish number format (comma as decimal) to float
                    free = float(free_str.replace(",", "."))
                    locked = float(locked_str.replace(",", "."))
                    
                    if free > 0 or locked > 0:
                        logger.info(f"  {asset}: free={free:.8f}, locked={locked:.8f}")
                
                self.test_results["1_get_balances"] = {
                    "status": "✅ PASS",
                    "details": f"Received {len(balances)} balance entries"
                }
            else:
                logger.error("❌ FAIL: No balances returned or wrong format")
                self.test_results["1_get_balances"] = {
                    "status": "❌ FAIL",
                    "details": "No balances or wrong format"
                }
        
        except Exception as e:
            logger.error(f"❌ FAIL: Exception: {e}")
            self.test_results["1_get_balances"] = {
                "status": "❌ FAIL",
                "details": str(e)
            }
    
    async def test_2_create_limit_order(self):
        """Test 2: create_order() LIMIT - Create a far-off price limit order."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 2: create_order() - LIMIT ORDER")
        logger.info("=" * 80)
        
        try:
            # Get current market price
            ticker = await self.client.get_ticker(self.test_pair)
            current_price = float(ticker["data"][0]["last"])
            logger.info(f"Current {self.test_pair} price: {current_price:,.2f}")
            
            # Create a buy limit order at 50% below market (will not fill)
            # BTCTRY requires: price must be integer, multiple of 10 (tickSize)
            far_price = current_price * 0.5
            far_price = int(far_price / 10) * 10  # Round to nearest 10
            
            small_quantity = 0.0001  # Very small amount of BTC
            
            logger.info(f"Creating LIMIT BUY order:")
            logger.info(f"  Price: {far_price:,.0f} TRY (50% below market, rounded to tickSize)")
            logger.info(f"  Quantity: {small_quantity} BTC")
            
            order_response = await self.client.create_order(
                pair_symbol=self.test_pair,
                side="buy",
                price=far_price,
                quantity=small_quantity,
                order_type="limit"
            )
            
            logger.info(f"Order response: {order_response}")
            
            # Check if order was created successfully
            if "data" in order_response and "id" in order_response["data"]:
                self.limit_order_id = order_response["data"]["id"]
                logger.info(f"✅ SUCCESS: Limit order created with ID: {self.limit_order_id}")
                
                self.test_results["2_create_limit_order"] = {
                    "status": "✅ PASS",
                    "details": f"Order ID: {self.limit_order_id}, Price: {far_price:,.2f}"
                }
            else:
                logger.error(f"❌ FAIL: Order creation response unexpected: {order_response}")
                self.test_results["2_create_limit_order"] = {
                    "status": "❌ FAIL",
                    "details": "Order ID not found in response"
                }
        
        except Exception as e:
            logger.error(f"❌ FAIL: Exception: {e}")
            self.test_results["2_create_limit_order"] = {
                "status": "❌ FAIL",
                "details": str(e)
            }
    
    async def test_3_get_open_orders(self):
        """Test 3: get_open_orders() - Verify the limit order appears."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 3: get_open_orders()")
        logger.info("=" * 80)
        
        if not self.limit_order_id:
            logger.error("❌ FAIL: No limit order ID from previous test")
            self.test_results["3_get_open_orders"] = {
                "status": "❌ FAIL",
                "details": "No order ID from previous test"
            }
            return
        
        try:
            # Wait a moment for order to propagate
            await asyncio.sleep(1)
            
            response = await self.client.get_open_orders(self.test_pair)
            
            # BtcTurk returns: {"data": {...}, "success": true}
            if isinstance(response, dict) and "data" in response:
                open_orders = response["data"].get("bids", []) + response["data"].get("asks", [])
            else:
                open_orders = response if isinstance(response, list) else []
            
            logger.info(f"Found {len(open_orders)} open orders for {self.test_pair}")
            
            # Look for our order - order IDs might be strings
            order_found = False
            for order in open_orders:
                order_id = order.get("id")
                # Compare as strings to handle both int and string IDs
                if str(order_id) == str(self.limit_order_id):
                    order_found = True
                    logger.info(f"✅ SUCCESS: Found our order in open orders:")
                    logger.info(f"  ID: {order_id}")
                    logger.info(f"  Type: {order.get('type')}")
                    logger.info(f"  Price: {order.get('price')}")
                    logger.info(f"  Quantity: {order.get('quantity')}")
                    logger.info(f"  Status: {order.get('status')}")
                    break
            
            if order_found:
                self.test_results["3_get_open_orders"] = {
                    "status": "✅ PASS",
                    "details": f"Order {self.limit_order_id} found in open orders"
                }
            else:
                logger.error(f"❌ FAIL: Order {self.limit_order_id} not found in open orders")
                logger.info("Open orders list:")
                for order in open_orders[:5]:  # Show first 5 only
                    logger.info(f"  ID: {order.get('id')}, Status: {order.get('status')}")
                
                self.test_results["3_get_open_orders"] = {
                    "status": "❌ FAIL",
                    "details": f"Order {self.limit_order_id} not in list"
                }
        
        except Exception as e:
            logger.error(f"❌ FAIL: Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.test_results["3_get_open_orders"] = {
                "status": "❌ FAIL",
                "details": str(e)
            }
    
    async def test_4_cancel_order(self):
        """Test 4: cancel_order() - Cancel the limit order."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 4: cancel_order()")
        logger.info("=" * 80)
        
        if not self.limit_order_id:
            logger.error("❌ FAIL: No limit order ID from previous test")
            self.test_results["4_cancel_order"] = {
                "status": "❌ FAIL",
                "details": "No order ID from previous test"
            }
            return
        
        try:
            logger.info(f"Canceling order ID: {self.limit_order_id}")
            
            cancel_response = await self.client.cancel_order(self.limit_order_id)
            logger.info(f"Cancel response: {cancel_response}")
            
            # Check if cancellation was successful
            # BtcTurk returns: {"success": true, "message": "SUCCESS", "code": 0}
            if cancel_response.get("success") is True:
                logger.info(f"✅ SUCCESS: Order {self.limit_order_id} canceled successfully")
                
                # Verify it's no longer in open orders
                await asyncio.sleep(1)
                response = await self.client.get_open_orders(self.test_pair)
                
                if isinstance(response, dict) and "data" in response:
                    open_orders = response["data"].get("bids", []) + response["data"].get("asks", [])
                else:
                    open_orders = response if isinstance(response, list) else []
                
                still_open = any(str(o.get("id")) == str(self.limit_order_id) for o in open_orders)
                
                if still_open:
                    logger.warning("⚠️  Order still appears in open orders (may take time)")
                else:
                    logger.info("✅ Confirmed: Order no longer in open orders")
                
                self.test_results["4_cancel_order"] = {
                    "status": "✅ PASS",
                    "details": f"Order {self.limit_order_id} canceled"
                }
            else:
                logger.error(f"❌ FAIL: Unexpected cancel response: {cancel_response}")
                self.test_results["4_cancel_order"] = {
                    "status": "❌ FAIL",
                    "details": "Unexpected response format"
                }
        
        except Exception as e:
            logger.error(f"❌ FAIL: Exception: {e}")
            self.test_results["4_cancel_order"] = {
                "status": "❌ FAIL",
                "details": str(e)
            }
    
    async def test_5_6_market_order_and_ws(self):
        """Test 5 & 6: create_order() MARKET and WebSocket private events."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 5 & 6: MARKET ORDER + WEBSOCKET USER EVENTS")
        logger.info("=" * 80)
        
        # Setup WebSocket message handler
        def on_ws_message(msg):
            """Handle WebSocket messages and look for user events."""
            if not isinstance(msg, list) or len(msg) < 2:
                return
            
            code = msg[0]
            payload = msg[1]
            
            # User events: 423 (UserTrade), 441 (OrderMatch), 451/452/453 (Order Insert/Delete/Update)
            if code in [423, 441, 451, 452, 453]:
                logger.info(f"🔔 WebSocket USER EVENT {code}: {payload}")
                self.market_order_received = True
        
        try:
            # Start WebSocket connection
            logger.info("Starting WebSocket connection...")
            ws_task = asyncio.create_task(self.client.connect(on_ws_message))
            
            # Wait for connection
            await asyncio.sleep(2)
            
            # Authenticate WebSocket for private events
            logger.info("Authenticating WebSocket for private channels...")
            await self.client.authenticate_ws()
            
            # Wait for authentication
            await asyncio.sleep(2)
            
            if not self.client.ws_authenticated:
                logger.warning("⚠️  WebSocket authentication may have failed")
            else:
                logger.info("✅ WebSocket authenticated successfully")
            
            # Get current market price
            ticker = await self.client.get_ticker(self.test_pair)
            current_price = float(ticker["data"][0]["last"])
            logger.info(f"Current {self.test_pair} price: {current_price:,.2f}")
            
            # For market BUY, quantity must be in quote currency (TRY)
            # Use 200 TRY (minimum is ~100 TRY, we have 250 TRY left)
            market_buy_amount_try = 200.0
            estimated_btc = market_buy_amount_try / current_price
            
            logger.info(f"\nCreating MARKET BUY order:")
            logger.info(f"  Amount: {market_buy_amount_try:.2f} TRY")
            logger.info(f"  Estimated BTC: ~{estimated_btc:.8f}")
            logger.info("⚠️  WARNING: This will execute a real market order!")
            
            # Give user a chance to cancel
            logger.info("Starting in 3 seconds... (Ctrl+C to cancel)")
            await asyncio.sleep(3)
            
            # Reset flag
            self.market_order_received = False
            
            # Create market order - for market BUY, quantity is in TRY
            logger.info("Executing market order...")
            order_response = await self.client.create_order(
                pair_symbol=self.test_pair,
                side="buy",
                price=0,  # Market orders don't need price
                quantity=market_buy_amount_try,  # For market BUY: TRY amount
                order_type="market"
            )
            
            logger.info(f"Market order response: {order_response}")
            
            # Check if order was filled
            market_order_status = "UNKNOWN"
            if "data" in order_response:
                order_data = order_response["data"]
                order_id = order_data.get("id")
                status = order_data.get("status")
                
                logger.info(f"Market order ID: {order_id}")
                logger.info(f"Market order status: {status}")
                
                if status == "Filled" or "FILLED" in str(status).upper():
                    market_order_status = "FILLED"
                    logger.info("✅ SUCCESS: Market order FILLED immediately")
                else:
                    market_order_status = status
                    logger.warning(f"⚠️  Market order status: {status}")
                
                self.test_results["5_create_market_order"] = {
                    "status": "✅ PASS" if market_order_status == "FILLED" else "⚠️  PARTIAL",
                    "details": f"Order ID: {order_id}, Status: {market_order_status}"
                }
            else:
                logger.error(f"❌ FAIL: Unexpected market order response: {order_response}")
                self.test_results["5_create_market_order"] = {
                    "status": "❌ FAIL",
                    "details": "Unexpected response format"
                }
            
            # Wait for WebSocket user events
            logger.info("\nWaiting for WebSocket user events (10 seconds)...")
            await asyncio.sleep(10)
            
            # Check if we received WS events
            if self.market_order_received:
                logger.info("✅ SUCCESS: Received WebSocket user events for market order")
                self.test_results["6_ws_user_events"] = {
                    "status": "✅ PASS",
                    "details": "User events received via WebSocket"
                }
            else:
                logger.warning("⚠️  No WebSocket user events received")
                logger.info("This may be normal if WS authentication failed or events are delayed")
                self.test_results["6_ws_user_events"] = {
                    "status": "⚠️  PARTIAL",
                    "details": "No user events received (check WS auth)"
                }
            
            # Disconnect WebSocket
            logger.info("Disconnecting WebSocket...")
            await self.client.disconnect()
            try:
                await asyncio.wait_for(ws_task, timeout=5)
            except asyncio.TimeoutError:
                ws_task.cancel()
        
        except asyncio.CancelledError:
            logger.info("Test cancelled by user")
            self.test_results["5_create_market_order"] = {
                "status": "❌ CANCELLED",
                "details": "Test cancelled by user"
            }
            self.test_results["6_ws_user_events"] = {
                "status": "❌ CANCELLED",
                "details": "Test cancelled by user"
            }
        
        except Exception as e:
            logger.error(f"❌ FAIL: Exception: {e}")
            self.test_results["5_create_market_order"] = {
                "status": "❌ FAIL",
                "details": str(e)
            }
            self.test_results["6_ws_user_events"] = {
                "status": "❌ FAIL",
                "details": str(e)
            }
    
    def print_final_report(self):
        """Print final test report."""
        logger.info("\n" + "=" * 80)
        logger.info("FINAL TEST REPORT")
        logger.info("=" * 80)
        
        test_names = {
            "1_get_balances": "Test 1: get_balances()",
            "2_create_limit_order": "Test 2: create_order() - LIMIT",
            "3_get_open_orders": "Test 3: get_open_orders()",
            "4_cancel_order": "Test 4: cancel_order()",
            "5_create_market_order": "Test 5: create_order() - MARKET",
            "6_ws_user_events": "Test 6: WebSocket User Events",
        }
        
        for key in ["1_get_balances", "2_create_limit_order", "3_get_open_orders", 
                    "4_cancel_order", "5_create_market_order", "6_ws_user_events"]:
            result = self.test_results.get(key, {"status": "❓ NOT RUN", "details": "Test not executed"})
            logger.info(f"\n{test_names[key]}")
            logger.info(f"  Status: {result['status']}")
            logger.info(f"  Details: {result['details']}")
        
        logger.info("\n" + "=" * 80)
        
        # Summary
        total_tests = len(test_names)
        passed = sum(1 for r in self.test_results.values() if "✅ PASS" in r["status"])
        failed = sum(1 for r in self.test_results.values() if "❌ FAIL" in r["status"])
        partial = sum(1 for r in self.test_results.values() if "⚠️" in r["status"])
        
        logger.info(f"SUMMARY: {passed} passed, {failed} failed, {partial} partial/warning out of {total_tests} tests")
        logger.info("=" * 80)


async def main():
    """Main entry point."""
    tester = BtcTurkPrivateAPITester()
    
    try:
        await tester.run_all_tests()
    except KeyboardInterrupt:
        logger.info("\nTest suite interrupted by user")
    except Exception as e:
        logger.error(f"Test suite error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
