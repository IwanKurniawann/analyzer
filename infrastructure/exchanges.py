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
    Fokus pada penanganan error yang tangguh, koneksi yang stabil, dan dukungan proxy.
    Kunci API sekarang bersifat opsional untuk koneksi publik saja.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, passphrase: Optional[str] = None, http_proxy: Optional[str] = None, https_proxy: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.http_proxy = http_proxy
        self.https_proxy = https_proxy
        self.exchange: Optional[ccxt.kucoin] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.is_public_only = not (api_key and api_secret and passphrase)
        if self.is_public_only:
            self.logger.warning("API keys not provided. Initializing in public-only mode. Private endpoints will fail.")

    async def initialize(self) -> None:
        """Inisialisasi instance bursa CCXT untuk mode LIVE dengan penanganan error dan proxy."""
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

            # Hanya tambahkan kredensial jika semuanya tersedia
            if not self.is_public_only:
                config['apiKey'] = self.api_key
                config['secret'] = self.api_secret
                config['password'] = self.passphrase
            
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
            # Muat pasar (mungkin gagal pada panggilan privat jika dalam mode publik)
            try:
                await self.exchange.load_markets()
            except ccxt.AuthenticationError as auth_err:
                if self.is_public_only:
                    self.logger.warning(f"Could not load all market data due to public-only mode: {auth_err}")
                else:
                    raise auth_err

            self.logger.info(f"✅ KuCoin exchange initialized. Mode: {'Public-Only' if self.is_public_only else 'Private'}")

        except ccxt.ExchangeError as e:
            if "unavailable in the U.S." in str(e):
                self.logger.error("❌ Geo-restriction error from KuCoin. The server IP is likely in a restricted region (e.g., USA). The proxy is required.", exc_info=False)
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
            await self.exchange.fetch_time()
            return True
        except Exception as e:
            self.logger.error(f"Exchange connection test failed: {e}")
            return False

    async def get_ohlcv_data(self, symbol: str, timeframe: str, limit: int = 100) -> List[MarketData]:
        if not self.exchange:
            raise ConnectionError("KuCoin exchange is not initialized. Cannot fetch data.")
        try:
            if symbol not in self.exchange.markets:
                await self.exchange.load_markets(True) # Coba muat ulang pasar jika simbol tidak ditemukan
                if symbol not in self.exchange.markets:
                    raise ValueError(f"Symbol {symbol} not found in KuCoin markets after reload")
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
            
    async def get_latest_price(self, symbol: str) -> float:
        if not self.exchange: raise ConnectionError("Exchange not initialized.")
        ticker = await self.exchange.fetch_ticker(symbol)
        return float(ticker['last'])

    async def get_exchange_info(self) -> Dict[str, Any]:
        if not self.exchange: raise ConnectionError("Exchange not initialized.")
        return {"name": "KuCoin", "live": True, "markets": len(self.exchange.markets)}

