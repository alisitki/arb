#!/usr/bin/env python3
"""
BTC/USDT Spread Monitor
Monitors real-time price spread between Binance and BtcTurk for BTC/USDT pair.
Logs data to console (with colors) and CSV file.
Only reads data, no trading operations.
Note: Uses USDT/TRY stream for latency measurement (more frequent trades).
"""

import asyncio
import csv
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from exchange_clients.binance_client import BinanceClient
from exchange_clients.btcturk_client import BtcturkClient

# Load environment variables
load_dotenv()

# Setup logging for BtcTurk client - only WARNING and above
logging.basicConfig(
    level=logging.INFO,  # Temporarily set to INFO for debugging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# ANSI Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class SpreadMonitor:
    """Monitor and log spread between Binance and BtcTurk for BTC/USDT."""
    
    def __init__(self, csv_filename: str = "spread_log.csv"):
        # Initialize clients
        self.binance = BinanceClient(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", "")
        )
        self.btcturk = BtcturkClient()
        
        # Price tracking
        self.binance_bid: Optional[float] = None
        self.binance_ask: Optional[float] = None
        self.btcturk_bid: Optional[float] = None
        self.btcturk_ask: Optional[float] = None
        
        # CSV file
        self.csv_filename = csv_filename
        self.csv_path = Path(csv_filename)
        self._init_csv()
        
        # Control flag
        self.running = True
        
    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not self.csv_path.exists():
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'binance_bid',
                    'binance_ask',
                    'btcturk_bid',
                    'btcturk_ask',
                    'spread_try',
                    'spread_pct',
                    'binance_event_latency_ms',
                    'binance_rtt_latency_ms',
                    'btcturk_event_latency_ms',
                    'btcturk_rtt_latency_ms'
                ])
            print(f"{Colors.OKGREEN}✓ Created CSV file: {self.csv_filename}{Colors.ENDC}")
        else:
            print(f"{Colors.OKCYAN}✓ Using existing CSV file: {self.csv_filename}{Colors.ENDC}")
    
    def _write_to_csv(self, data: dict):
        """Append data row to CSV file."""
        try:
            with open(self.csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    data['timestamp'],
                    data['binance_bid'],
                    data['binance_ask'],
                    data['btcturk_bid'],
                    data['btcturk_ask'],
                    data['spread_try'],
                    data['spread_pct'],
                    data['binance_event_latency_ms'],
                    data['binance_rtt_latency_ms'],
                    data['btcturk_event_latency_ms'],
                    data['btcturk_rtt_latency_ms']
                ])
        except Exception as e:
            print(f"{Colors.FAIL}Error writing to CSV: {e}{Colors.ENDC}")
        
    async def on_binance_message(self, data: dict):
        """Handle Binance WebSocket messages."""
        try:
            # Binance sends multi-stream format
            if "stream" in data and "data" in data:
                stream = data["stream"]
                payload = data["data"]
                
                # BTC/USDT price data (main pair for arbitrage)
                if "btcusdt@aggTrade" in stream:
                    trade_price = float(payload.get("p", 0))
                    # Approximate bid/ask from last trade price (minimal spread)
                    self.binance_bid = trade_price - 0.01  # Slight offset for bid
                    self.binance_ask = trade_price + 0.01  # Slight offset for ask
                
                # USDT/TRY for latency measurement only (more frequent trades)
                elif "usdttry@aggTrade" in stream:
                    # Calculate event latency from USDT/TRY stream
                    event_time_ms = payload.get("E")  # Event time in milliseconds
                    if event_time_ms:
                        recv_time_ms = time.time() * 1000
                        latency_ms = recv_time_ms - event_time_ms
                        
                        # Update with EMA smoothing
                        if 0 <= latency_ms <= 10000:  # Sanity check: 0-10 seconds
                            if self.binance.latency_event > 0:
                                alpha = 0.3
                                self.binance.latency_event = alpha * latency_ms + (1 - alpha) * self.binance.latency_event
                            else:
                                self.binance.latency_event = latency_ms
                
                # Keep bookTicker support as fallback
                elif "btcusdt@bookTicker" in stream:
                    self.binance_bid = float(payload.get("b", 0))
                    self.binance_ask = float(payload.get("a", 0))
        except Exception as e:
            print(f"Error processing Binance message: {e}")
    
    async def setup_binance(self):
        """Setup Binance WebSocket connection."""
        # Subscribe to BTC/USDT aggregate trades for price data
        self.binance.streams.append("btcusdt@aggTrade")
        
        # Also subscribe to USDT/TRY for latency measurement (more frequent trades)
        self.binance.streams.append("usdttry@aggTrade")
        
        # Start WebSocket connection in background
        asyncio.create_task(self.binance.connect(self.on_binance_message))
        
        print(f"{Colors.OKGREEN}✓ Binance WebSocket subscribed to BTCUSDT + USDTTRY{Colors.ENDC}")
    
    def on_btcturk_message(self, msg: dict):
        """Handle BtcTurk WebSocket messages."""
        # Silently handle messages - orderbook is updated internally by btcturk_client
        pass
    
    async def setup_btcturk(self):
        """Setup BtcTurk WebSocket connection."""
        # Start WebSocket connection in background with callback
        asyncio.create_task(self.btcturk.connect(on_message=self.on_btcturk_message))
        
        # Wait a bit for connection to establish
        await asyncio.sleep(2)
        
        # Subscribe to BTCUSDT orderbook for price data
        await self.btcturk.subscribe_orderbook("BTCUSDT")
        
        # Subscribe to USDTTRY trade for latency measurement (more frequent trades)
        await self.btcturk.subscribe_trade("USDTTRY")
        
        print(f"{Colors.OKGREEN}✓ BtcTurk WebSocket subscribed to BTCUSDT + USDTTRY{Colors.ENDC}")
    
    def get_btcturk_best_prices(self) -> tuple[Optional[float], Optional[float]]:
        """Get best bid/ask from BtcTurk orderbook."""
        try:
            ob = self.btcturk.orderbooks.get("BTCUSDT", {})
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            
            best_bid = bids[0][0] if bids else None
            best_ask = asks[0][0] if asks else None
            
            return best_bid, best_ask
        except Exception as e:
            print(f"Error getting BtcTurk prices: {e}")
            return None, None
    
    def calculate_spread(self) -> tuple[Optional[float], Optional[float]]:
        """
        Calculate spread between exchanges.
        
        Returns:
            (spread_usdt, spread_percent) or (None, None) if data incomplete
        """
        if not all([self.binance_ask, self.btcturk_bid]):
            return None, None
        
        # Spread = BtcTurk bid - Binance ask (arbitrage opportunity if positive)
        spread_usdt = self.btcturk_bid - self.binance_ask
        spread_percent = (spread_usdt / self.binance_ask) * 100
        
        return spread_usdt, spread_percent
    
    def log_spread(self):
        """Log current spread information in single line (colored) and save to CSV."""
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S.%f")[:-3]
        timestamp_full = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Update BtcTurk prices from orderbook
        self.btcturk_bid, self.btcturk_ask = self.get_btcturk_best_prices()
        
        # Calculate spread
        spread_usdt, spread_percent = self.calculate_spread()
        
        # Get latencies (already in milliseconds from clients)
        # Binance: prefer event latency, fallback to RTT
        binance_event_latency = round(self.binance.latency_event, 2) if hasattr(self.binance, 'latency_event') and self.binance.latency_event > 0 else None
        binance_rtt_latency = round(self.binance.latency_rtt, 2) if hasattr(self.binance, 'latency_rtt') and self.binance.latency_rtt > 0 else None
        
        # BTCTurk: prefer event latency, fallback to RTT
        btcturk_event_latency = round(self.btcturk.latency_event, 2) if hasattr(self.btcturk, 'latency_event') and self.btcturk.latency_event > 0 else None
        btcturk_rtt_latency = round(self.btcturk.latency_rtt, 2) if hasattr(self.btcturk, 'latency_rtt') and self.btcturk.latency_rtt > 0 else None
        
        # Format prices (all in USDT)
        binance_bid_str = f"{self.binance_bid:.2f}" if self.binance_bid else "N/A"
        binance_ask_str = f"{self.binance_ask:.2f}" if self.binance_ask else "N/A"
        btcturk_bid_str = f"{self.btcturk_bid:.2f}" if self.btcturk_bid else "N/A"
        btcturk_ask_str = f"{self.btcturk_ask:.2f}" if self.btcturk_ask else "N/A"
        
        if spread_usdt is not None and spread_percent is not None:
            spread_usdt_str = f"{spread_usdt:+.2f}"
            spread_pct_str = f"{spread_percent:+.2f}%"
            
            # Color code based on spread
            if spread_percent > 0.1:
                spread_color = Colors.OKGREEN  # Good arbitrage opportunity
            elif spread_percent > 0:
                spread_color = Colors.OKCYAN   # Small positive spread
            elif spread_percent > -0.1:
                spread_color = Colors.WARNING  # Small negative spread
            else:
                spread_color = Colors.FAIL     # Negative spread
        else:
            spread_usdt_str = "N/A"
            spread_pct_str = "N/A"
            spread_color = Colors.ENDC
        
        # Latency strings
        # Binance: show event latency if available, otherwise RTT
        if binance_event_latency is not None:
            binance_lat_str = f"{binance_event_latency}ms"
        elif binance_rtt_latency is not None:
            binance_lat_str = f"{binance_rtt_latency}ms(rtt)"
        else:
            binance_lat_str = "N/A"
        
        # BTCTurk: show event latency if available, otherwise RTT
        if btcturk_event_latency is not None:
            btcturk_lat_str = f"{btcturk_event_latency}ms"
        elif btcturk_rtt_latency is not None:
            btcturk_lat_str = f"{btcturk_rtt_latency}ms(rtt)"
        else:
            btcturk_lat_str = "N/A"
        
        # Single line log (colored)
        log_line = (
            f"{Colors.BOLD}{time_str}{Colors.ENDC} | "
            f"{Colors.OKBLUE}Binance:{Colors.ENDC} {binance_bid_str}/{binance_ask_str} "
            f"({binance_lat_str}) | "
            f"{Colors.OKCYAN}BtcTurk:{Colors.ENDC} {btcturk_bid_str}/{btcturk_ask_str} "
            f"({btcturk_lat_str}) | "
            f"{spread_color}Spread:{Colors.ENDC} {spread_usdt_str} USDT ({spread_pct_str})"
        )
        
        print(log_line)
        
        # Prepare data for CSV
        csv_data = {
            'timestamp': timestamp_full,
            'binance_bid': self.binance_bid if self.binance_bid is not None else '',
            'binance_ask': self.binance_ask if self.binance_ask is not None else '',
            'btcturk_bid': self.btcturk_bid if self.btcturk_bid is not None else '',
            'btcturk_ask': self.btcturk_ask if self.btcturk_ask is not None else '',
            'spread_try': spread_usdt if spread_usdt is not None else '',
            'spread_pct': spread_percent if spread_percent is not None else '',
            'binance_event_latency_ms': binance_event_latency if binance_event_latency is not None else '',
            'binance_rtt_latency_ms': binance_rtt_latency if binance_rtt_latency is not None else '',
            'btcturk_event_latency_ms': btcturk_event_latency if btcturk_event_latency is not None else '',
            'btcturk_rtt_latency_ms': btcturk_rtt_latency if btcturk_rtt_latency is not None else ''
        }
        
        # Write to CSV
        self._write_to_csv(csv_data)
    
    async def monitor_loop(self):
        """Main monitoring loop - logs spread every 500ms."""
        while self.running:
            try:
                self.log_spread()
                await asyncio.sleep(0.5)  # 500ms
            except Exception as e:
                print(f"Error in monitor loop: {e}")
                await asyncio.sleep(0.5)
    
    async def start(self):
        """Start the spread monitor."""
        print(f"{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}BTC/TRY Spread Monitor - Starting...{Colors.ENDC}")
        print(f"{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
        
        # Setup both exchanges
        await self.setup_binance()
        await self.setup_btcturk()
        
        # Wait for initial data
        print(f"\n{Colors.WARNING}Waiting for initial data...{Colors.ENDC}")
        await asyncio.sleep(3)
        
        print(f"\n{Colors.OKGREEN}Monitoring started (Ctrl+C to stop):{Colors.ENDC}")
        print(f"{Colors.OKGREEN}{'-' * 80}{Colors.ENDC}\n")
        
        # Start monitoring loop
        await self.monitor_loop()
    
    async def stop(self):
        """Stop the monitor and cleanup."""
        print(f"\n{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.WARNING}Stopping spread monitor...{Colors.ENDC}")
        self.running = False
        
        # Disconnect clients
        await self.binance.disconnect()
        await self.btcturk.disconnect()
        await self.btcturk.close()
        
        print(f"{Colors.OKGREEN}✓ Disconnected from all exchanges{Colors.ENDC}")
        print(f"{Colors.OKGREEN}✓ CSV file saved: {self.csv_filename}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'=' * 80}{Colors.ENDC}")


async def main():
    """Main entry point."""
    monitor = SpreadMonitor()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\n\nReceived interrupt signal...")
        asyncio.create_task(monitor.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await monitor.start()
    except KeyboardInterrupt:
        pass
    finally:
        await monitor.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
