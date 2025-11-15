# BtcTurk API Credentials Setup

## Current Status

Your `.env` file currently has WebSocket credentials:
- ✅ `BTC_TURK_Public_Key` (for WebSocket)
- ✅ `BTC_TURK_Private_Key` (for WebSocket)

## Missing Credentials

For REST API private endpoints (balances, orders, etc.), you need:
- ❌ `BTC_TURK_API_KEY` (for REST API)
- ❌ `BTC_TURK_API_SECRET` (for REST API)

## How to Get REST API Credentials

1. Go to BtcTurk website: https://pro.btcturk.com
2. Login to your account
3. Navigate to: **Settings** → **API** (or direct link: https://pro.btcturk.com/api)
4. Create a new API key with the following permissions:
   - ✅ View balance
   - ✅ Place order
   - ✅ Cancel order
   - ✅ View open orders
5. Copy the **API Key** and **Secret Key**
6. Add them to your `.env` file

## Update Your .env File

Add these two lines to your `.env` file:

```bash
# REST API Credentials
BTC_TURK_API_KEY=your_api_key_here
BTC_TURK_API_SECRET=your_api_secret_here

# WebSocket Credentials (already present)
BTC_TURK_Public_Key=f5df25b7-982a-4ec7-b6d1-b871b52277d5
BTC_TURK_Private_Key=TLMozWmce0H0/IYfTffIB21tcHsCPcbD
```

## Security Notes

⚠️ **Important Security Warnings:**
- Never share your API credentials with anyone
- Never commit `.env` file to git
- Use IP whitelist if available
- Start with minimal permissions for testing
- Keep your Secret Key secure - it cannot be recovered if lost

## After Adding Credentials

Once you've added the REST API credentials to `.env`, run the test again:

```bash
python3 test_btcturk_private.py
```

The test will:
1. ✅ Get your balances
2. ✅ Create a limit order (far from market, won't fill)
3. ✅ Verify the order appears in open orders
4. ✅ Cancel the limit order
5. ⚠️ Create a small MARKET order (will execute!)
6. ✅ Monitor WebSocket for fill events

## WebSocket Authentication Issue

Note: The test also showed a WebSocket authentication issue:
```
Unauthorized - Invalid Nonce
```

This might be because:
- The WebSocket credentials might need to be regenerated
- Or the nonce algorithm needs adjustment

We'll address this after REST API tests are working.
