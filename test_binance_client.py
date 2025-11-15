import asyncio
import time
from exchange_clients.binance_client import BinanceClient
import json

API_KEY = "BURAYA_API_KEY"
API_SECRET = "BURAYA_SECRET"


# ============================================================
# 🔥 1) WebSocket mesaj callback
# ============================================================
async def on_message(msg):
    t = time.time()
    if "stream" in msg:
        stream = msg["stream"]

        # trade
        if "@trade" in stream:
            print("[TRADE]", msg["data"]["p"])

        # depth update
        if "@depth" in stream:
            print("[DEPTH] update received")

        # user data stream
        if "executionReport" in json.dumps(msg):
            print("🔥 ORDER EVENT:", msg)


# ============================================================
# 🔥 2) ANA TEST FONKSİYONU
# ============================================================
async def full_test():

    print("\n=== Binance Client Full Test Başlıyor ===\n")

    client = BinanceClient(API_KEY, API_SECRET)
    ws_task = None

    try:
        # ----------------------------------------------------------
        # 1) UserStream / listenKey → FILLED eventleri için ŞART
        # ----------------------------------------------------------
        print("\n[1] UserDataStream listenKey alınıyor...")
        await client.start_user_stream()
        
        has_valid_api_key = bool(client.listen_key)
        if has_valid_api_key:
            print("✅ listenKey:", client.listen_key)
        else:
            print("⚠️  listenKey alınamadı (API key gerekli testler atlanacak)")

        # ----------------------------------------------------------
        # 2) Orderbook snapshot
        # ----------------------------------------------------------
        print("\n[2] Orderbook snapshot alınıyor...")
        await client.load_orderbook_snapshot("BTCUSDT")
        print("✅ Snapshot loaded. best_bid:", client.orderbook["bids"][0])

        # ----------------------------------------------------------
        # 3) Streams tanımla
        # ----------------------------------------------------------
        print("\n[3] Stream listesi oluşturuluyor...")
        if has_valid_api_key:
            client.streams = [
                "btcusdt@trade",
                "btcusdt@depth@100ms",
                client.listen_key
            ]
            print("✅ Streams tanımlandı (trade, depth, userData)")
        else:
            client.streams = [
                "btcusdt@trade",
                "btcusdt@depth@100ms"
            ]
            print("✅ Streams tanımlandı (trade, depth - userData atlandı)")

        # ----------------------------------------------------------
        # 4) WS bağlantısını paralel çalıştır
        # ----------------------------------------------------------
        print("\n[4] WebSocket bağlantısı başlıyor...\n")

        ws_task = asyncio.create_task(client.connect(on_message))

        await asyncio.sleep(3)

        # ----------------------------------------------------------
        # 5) Market order TEST (en kritik test!) 
        # ----------------------------------------------------------
        if has_valid_api_key:
            print("\n[5] MARKET ORDER TEST ediliyor...")
            print("Küçük miktarda BTC alıyoruz...")

            order = await client.create_order(
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                quantity=0.0002
            )

            print("REST response:", order)
            print("🔥 Şimdi WS üzerinden FILLED eventi bekleniyor...\n")

            await asyncio.sleep(4)
        else:
            print("\n[5] MARKET ORDER TEST atlanıyor (geçerli API key yok)")
            await asyncio.sleep(2)

        # ----------------------------------------------------------
        # 6) Rate-limit Test
        # ----------------------------------------------------------
        print("\n[6] Rate-limit test ediliyor (20 request)...\n")
        for i in range(20):
            r = await client.rest_get("/api/v3/ticker/price", {"symbol": "BTCUSDT"})
            print(f"  {i+1}/20: {r}")

        print("✅ Rate-limit test tamam.")

        # ----------------------------------------------------------
        # 7) Reconnect Test
        # ----------------------------------------------------------
        if client.ws:
            print("\n[7] Reconnect test ediliyor... ws.close() çağırılıyor...")
            await client.ws.close()

            print("3 saniye bekleniyor...")
            await asyncio.sleep(3)

            print("✅ Eğer WS akışı yeniden başladıysa → reconnect OK\n")
        else:
            print("\n[7] Reconnect test atlanıyor (WS bağlantısı yok)")

        # ----------------------------------------------------------
        # 8) Latency Test
        # ----------------------------------------------------------
        print("\n[8] Latency test ediliyor (5 saniye)...")

        for i in range(5):
            print(f"  RTT {i+1}/5:", client.latency_rtt)
            await asyncio.sleep(1)

        print("✅ Latency test OK.")

        # ----------------------------------------------------------
        # Test bitti
        # ----------------------------------------------------------
        print("\n🎉 Tüm testler tamamlandı!")
        print("Eğer hatasız geçtiyse client tamamen hedge-ready.\n")

    finally:
        # Cleanup
        print("\n[CLEANUP] Bağlantı kapatılıyor...")
        await client.disconnect()
        if ws_task:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    asyncio.run(full_test())

