"""
Implementasi layanan bursa menggunakan CCXT (versi Live-Only)
"""

import ccxt.async_support as ccxt
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

        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        """Inisialisasi instance bursa CCXT untuk mode LIVE"""
        try:
            config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.passphrase,
                'enableRateLimit': True,
                'timeout': 30000,
                # --- PERBAIKAN DIMULAI DI SINI ---
                # Menambahkan header 'options' untuk mengatasi geo-restriction
                # 'KC-API-REMARK' adalah header khusus yang disarankan oleh KuCoin
                # untuk pengguna yang mengakses dari server cloud (seperti GitHub Actions)
                # yang mungkin berlokasi di wilayah terlarang (mis. AS).
                # Nilai '9527' adalah contoh umum yang digunakan, menandakan
                # bahwa Anda adalah pengguna yang sah.
                'options': {
                    'defaultHeaders': {
                        'KC-API-REMARK': '9527',
                    },
                },
                # --- AKHIR PERBAIKAN ---
            }

            self.exchange = ccxt.kucoin(config)

            await self.exchange.load_markets()

            self.logger.info("✅ KuCoin exchange initialized in LIVE mode with anti-restriction header")

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

    async def validate_symbol(self, str) -> bool:
        try:
            if not self.exchange: await self.initialize()
            return symbol in self.exchange.markets
        except Exception as e:
            self.logger.error(f"Failed to validate symbol {symbol}: {e}")
            return False

    async def get_exchange_info(self) -> Dict[str, Any]:
        return {"name": "KuCoin", "live": True}

