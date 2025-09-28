"""
Implementasi layanan bursa menggunakan CCXT (versi Live-Only yang Ditingkatkan)
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
    Implementasi KuCoin exchange yang ditingkatkan untuk lingkungan LIVE.
    Fokus pada penanganan error yang tangguh dan koneksi yang stabil.
    """

    def __init__(self, api_key: str, api_secret: str, passphrase: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.exchange: Optional[ccxt.kucoin] = None  # Menambahkan type hint
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self) -> None:
        """Inisialisasi instance bursa CCXT untuk mode LIVE dengan penanganan error."""
        try:
            config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.passphrase,
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {
                    'defaultHeaders': {
                        'KC-API-REMARK': '9527',  # Header anti-pembatasan geografis
                    },
                },
            }

            self.exchange = ccxt.kucoin(config)
            await self.exchange.load_markets()
            self.logger.info("✅ KuCoin exchange initialized in LIVE mode with anti-restriction header")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize KuCoin exchange: {e}", exc_info=True)
            # Pastikan self.exchange di-reset jika gagal
            if self.exchange:
                await self.exchange.close()
            self.exchange = None
            raise  # Melemparkan kembali exception agar proses utama berhenti

    async def close(self) -> None:
        """Menutup koneksi bursa dengan aman."""
        try:
            if self.exchange:
                await self.exchange.close()
                self.logger.info("🔒 Exchange connection closed")
        except Exception as e:
            self.logger.error(f"Error closing exchange: {e}")

    async def test_connection(self) -> bool:
        """Tes konektivitas bursa."""
        if not self.exchange:
            self.logger.error("Cannot test connection, exchange is not initialized.")
            return False
        try:
            await self.exchange.fetch_time()
            return True
        except Exception as e:
            self.logger.error(f"Exchange connection test failed: {e}")
            return False

    async def get_ohlcv_data(self, symbol: str, timeframe: str, limit: int = 100) -> List[MarketData]:
        if not self.exchange:
            raise ConnectionError("KuCoin exchange is not initialized. Cannot fetch data.")
        try:
            # ... (logika get_ohlcv_data tetap sama)
            if symbol not in self.exchange.markets:
                raise ValueError(f"Symbol {symbol} not found in KuCoin markets")
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv: return []
            return [MarketData(symbol=symbol, timeframe=timeframe, timestamp=datetime.fromtimestamp(i[0]/1000, tz=timezone.utc), open=i[1], high=i[2], low=i[3], close=i[4], volume=i[5]) for i in ohlcv]
        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV data for {symbol}: {e}")
            raise

    async def validate_symbol(self, symbol: str) -> bool:
        """Memvalidasi simbol dengan perbaikan bug."""
        if not self.exchange:
            self.logger.warning("Exchange not initialized, cannot validate symbol.")
            return False
        try:
            return symbol in self.exchange.markets
        except Exception as e:
            self.logger.error(f"Failed to validate symbol {symbol}: {e}")
            return False
            
    # Metode lain seperti get_latest_price dan get_exchange_info tetap sama
    # namun akan mendapat manfaat dari pemeriksaan 'if not self.exchange'
    async def get_latest_price(self, symbol: str) -> float:
        if not self.exchange: raise ConnectionError("Exchange not initialized.")
        ticker = await self.exchange.fetch_ticker(symbol)
        return float(ticker['last'])

    async def get_exchange_info(self) -> Dict[str, Any]:
        if not self.exchange: raise ConnectionError("Exchange not initialized.")
        return {"name": "KuCoin", "live": True, "markets": len(self.exchange.markets)}

