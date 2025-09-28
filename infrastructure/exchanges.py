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
    Implementasi KuCoin exchange untuk data publik saja.
    Fokus pada penanganan error yang tangguh, koneksi yang stabil, dan dukungan proxy.
    """

    def __init__(self, http_proxy: Optional[str] = None, https_proxy: Optional[str] = None):
        self.http_proxy = http_proxy
        self.https_proxy = https_proxy
        self.exchange: Optional[ccxt.kucoin] = None
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self) -> None:
        """Inisialisasi instance bursa CCXT untuk mode publik dengan penanganan error dan proxy."""
        try:
            config = {
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {
                    'defaultHeaders': {
                        'KC-API-REMARK': '9527',
                    },
                },
            }
            
            # Tambahkan konfigurasi proxy jika tersedia
            proxies = {}
            if self.http_proxy:
                proxies['http'] = self.http_proxy
            if self.https_proxy:
                proxies['https'] = self.https_proxy
            
            if proxies:
                config['proxies'] = proxies
                self.logger.info(f"🔌 Using proxies for exchange connection: {proxies}")

            self.exchange = ccxt.kucoin(config)
            # Muat pasar. Ini adalah titik di mana geo-restriction akan terjadi jika tidak ada proxy.
            await self.exchange.load_markets()

            self.logger.info("✅ KuCoin exchange initialized in Public-Only Mode.")

        except ccxt.ExchangeError as e:
            if "unavailable in the U.S." in str(e):
                self.logger.error("❌ Geo-restriction error from KuCoin. The server IP is in a restricted region (e.g., USA). A proxy is required.", exc_info=False)
            self.logger.error(f"❌ Failed to initialize KuCoin exchange: {e}", exc_info=True)
            if self.exchange:
                await self.exchange.close()
            self.exchange = None
            raise
        except Exception as e:
            self.logger.error(f"❌ An unexpected error occurred during KuCoin initialization: {e}", exc_info=True)
            if self.exchange:
                await self.exchange.close()
            self.exchange = None
            raise

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
            # Menggunakan endpoint publik yang berbeda untuk pengujian
            await self.exchange.fetch_status()
            return True
        except Exception as e:
            self.logger.error(f"Exchange connection test failed: {e}")
            return False

    async def get_ohlcv_data(self, symbol: str, timeframe: str, limit: int = 100) -> List[MarketData]:
        if not self.exchange:
            raise ConnectionError("KuCoin exchange is not initialized. Cannot fetch data.")
        try:
            if not self.exchange.markets:
                await self.exchange.load_markets(True)
            
            if symbol not in self.exchange.markets:
                raise ValueError(f"Symbol {symbol} not found in KuCoin markets after reload")
            
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv: return []
            return [MarketData(symbol=symbol, timeframe=timeframe, timestamp=datetime.fromtimestamp(i[0]/1000, tz=timezone.utc), open=i[1], high=i[2], low=i[3], close=i[4], volume=i[5]) for i in ohlcv]
        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV data for {symbol}: {e}")
            raise

    async def validate_symbol(self, symbol: str) -> bool:
        """Memvalidasi simbol."""
        if not self.exchange:
            self.logger.warning("Exchange not initialized, cannot validate symbol.")
            return False
        try:
            if not self.exchange.markets:
                await self.exchange.load_markets(True)
            return symbol in self.exchange.markets
        except Exception as e:
            self.logger.error(f"Failed to validate symbol {symbol}: {e}")
            return False
            
    async def get_latest_price(self, symbol: str) -> float:
        if not self.exchange: raise ConnectionError("Exchange not initialized.")
        ticker = await self.exchange.fetch_ticker(symbol)
        return float(ticker['last'])

    async def get_exchange_info(self) -> Dict[str, Any]:
        if not self.exchange: raise ConnectionError("Exchange not initialized.")
        return {"name": "KuCoin", "live": True, "markets": len(self.exchange.markets) if self.exchange.markets else 0}

