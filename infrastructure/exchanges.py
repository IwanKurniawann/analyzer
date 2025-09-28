"""
Implementasi layanan bursa menggunakan CCXT (versi Live-Only)
"""

import ccxt.async_support as ccxt # Menggunakan versi async_support yang lebih baik
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from domain.entities import MarketData
from domain.services import MarketDataService, ExchangeService

logger = logging.getLogger(__name__)

class KuCoinExchange(MarketDataService, ExchangeService):
    """
    Implementasi KuCoin exchange menggunakan CCXT untuk lingkungan LIVE.
    Logika sandbox telah dihapus sepenuhnya.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str, 
        passphrase: str,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.exchange = None
        self.logger = logging.getLogger(self.__class__.__name__)

        # Inisialisasi bursa saat objek dibuat
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        """Inisialisasi instance bursa CCXT untuk mode LIVE"""
        try:
            # Konfigurasi tidak lagi mengandung 'sandbox'
            config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.passphrase,
                'enableRateLimit': True,
                'timeout': 30000,
            }

            self.exchange = ccxt.kucoin(config)

            # Muat pasar
            await self.exchange.load_markets()

            self.logger.info("✅ KuCoin exchange initialized in LIVE mode")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize KuCoin exchange: {e}", exc_info=True)
            raise

    async def close(self) -> None:
        """Tutup koneksi bursa"""
        try:
            if self.exchange:
                await self.exchange.close()
                self.logger.info("🔒 Exchange connection closed")
        except Exception as e:
            self.logger.error(f"Error closing exchange: {e}")

    async def test_connection(self) -> bool:
        """Tes konektivitas bursa"""
        try:
            if not self.exchange:
                # Beri sedikit waktu untuk inisialisasi awal selesai
                await asyncio.sleep(1)
                if not self.exchange:
                    await self.initialize()

            if self.exchange:
                await self.exchange.fetch_time()
                return True
            else:
                self.logger.error("Exchange not initialized after delay")
                return False

        except Exception as e:
            self.logger.error(f"Exchange connection test failed: {e}")
            return False

    async def get_ohlcv_data(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[MarketData]:
        """Ambil data OHLCV dari KuCoin"""
        try:
            if not self.exchange: await self.initialize()

            if symbol not in self.exchange.markets:
                raise ValueError(f"Symbol {symbol} not found in KuCoin markets")

            ohlcv_data = await self.exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

            if not ohlcv_data:
                raise ValueError(f"No OHLCV data received for {symbol}")

            market_data_list = []
            for candle in ohlcv_data:
                ts, o, h, l, c, v = candle
                market_data = MarketData(
                    symbol=symbol, timeframe=timeframe,
                    timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                    open=float(o), high=float(h), low=float(l), close=float(c), 
                    volume=float(v) if v else 0.0
                )
                market_data_list.append(market_data)
            
            return market_data_list

        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV data for {symbol}: {e}")
            raise

    async def get_latest_price(self, symbol: str) -> float:
        try:
            if not self.exchange: await self.initialize()
            ticker = await self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            self.logger.error(f"Failed to get latest price for {symbol}: {e}")
            raise

    async def validate_symbol(self, symbol: str) -> bool:
        try:
            if not self.exchange: await self.initialize()
            return symbol in self.exchange.markets
        except Exception as e:
            self.logger.error(f"Failed to validate symbol {symbol}: {e}")
            return False

    async def get_exchange_info(self) -> Dict[str, Any]:
        return {"name": "KuCoin", "live": True}

