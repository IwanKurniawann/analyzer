"""
Exchange service implementation using CCXT
Concrete implementation untuk MarketDataService dan ExchangeService
"""

import ccxt
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from domain.entities import MarketData
from domain.services import MarketDataService, ExchangeService

logger = logging.getLogger(__name__)

class KuCoinExchange(MarketDataService, ExchangeService):
    """
    KuCoin exchange implementation using CCXT
    Provides market data dan exchange operations
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str, 
        passphrase: str,
        sandbox: bool = True,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.sandbox = sandbox
        self.exchange = None
        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize exchange
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        """Initialize CCXT exchange instance"""
        try:
            self.exchange = ccxt.kucoin({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.passphrase,
                'sandbox': self.sandbox,
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {
                    'adjustForTimeDifference': True,
                }
            })

            # Load markets
            await self.exchange.load_markets()

            self.logger.info(
                f"✅ KuCoin exchange initialized "
                f"({'sandbox' if self.sandbox else 'live'} mode)"
            )

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize KuCoin exchange: {e}")
            raise

    async def close(self) -> None:
        """Close exchange connection"""
        try:
            if self.exchange:
                await self.exchange.close()
                self.logger.info("🔒 Exchange connection closed")
        except Exception as e:
            self.logger.error(f"Error closing exchange: {e}")

    async def test_connection(self) -> bool:
        """Test exchange connectivity"""
        try:
            if not self.exchange:
                await self.initialize()

            # Test by fetching server time
            await self.exchange.fetch_time()
            return True

        except Exception as e:
            self.logger.error(f"Exchange connection test failed: {e}")
            return False

    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get exchange information and limits"""
        try:
            if not self.exchange:
                await self.initialize()

            info = {
                'exchange_name': 'KuCoin',
                'sandbox': self.sandbox,
                'rate_limit': self.exchange.rateLimit,
                'has': self.exchange.has,
                'markets_count': len(self.exchange.markets),
                'timeframes': list(self.exchange.timeframes.keys()) if self.exchange.timeframes else [],
            }

            return info

        except Exception as e:
            self.logger.error(f"Failed to get exchange info: {e}")
            return {}

    async def get_ohlcv_data(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[MarketData]:
        """
        Fetch OHLCV data dari KuCoin

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Timeframe (e.g., "1h", "4h", "1d")
            limit: Number of candles to fetch

        Returns:
            List of MarketData objects
        """
        try:
            if not self.exchange:
                await self.initialize()

            # Validate symbol
            if symbol not in self.exchange.markets:
                raise ValueError(f"Symbol {symbol} not found in KuCoin markets")

            # Fetch OHLCV data
            ohlcv_data = await self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )

            if not ohlcv_data:
                raise ValueError(f"No OHLCV data received for {symbol}")

            # Convert to MarketData objects
            market_data_list = []
            for candle in ohlcv_data:
                timestamp_ms, open_price, high_price, low_price, close_price, volume = candle

                market_data = MarketData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                    open=float(open_price),
                    high=float(high_price), 
                    low=float(low_price),
                    close=float(close_price),
                    volume=float(volume) if volume else 0.0
                )

                market_data_list.append(market_data)

            self.logger.debug(
                f"📊 Fetched {len(market_data_list)} OHLCV records for {symbol} ({timeframe})"
            )

            return market_data_list

        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV data for {symbol}: {e}")
            raise

    async def get_latest_price(self, symbol: str) -> float:
        """
        Get latest ticker price untuk symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest price
        """
        try:
            if not self.exchange:
                await self.initialize()

            ticker = await self.exchange.fetch_ticker(symbol)

            if not ticker or 'last' not in ticker:
                raise ValueError(f"No ticker data for {symbol}")

            return float(ticker['last'])

        except Exception as e:
            self.logger.error(f"Failed to get latest price for {symbol}: {e}")
            raise

    async def validate_symbol(self, symbol: str) -> bool:
        """
        Validate if symbol exists in exchange

        Args:
            symbol: Trading pair symbol

        Returns:
            True if symbol is valid
        """
        try:
            if not self.exchange:
                await self.initialize()

            return symbol in self.exchange.markets

        except Exception as e:
            self.logger.error(f"Failed to validate symbol {symbol}: {e}")
            return False

    async def get_markets(self) -> Dict[str, Any]:
        """
        Get available markets/symbols

        Returns:
            Dict of available markets
        """
        try:
            if not self.exchange:
                await self.initialize()

            return self.exchange.markets

        except Exception as e:
            self.logger.error(f"Failed to get markets: {e}")
            return {}

    async def fetch_balance(self) -> Dict[str, Any]:
        """
        Fetch account balance (requires trade permission)

        Returns:
            Account balance information
        """
        try:
            if not self.exchange:
                await self.initialize()

            balance = await self.exchange.fetch_balance()
            return balance

        except Exception as e:
            self.logger.error(f"Failed to fetch balance: {e}")
            # Don't raise - balance might not be needed for signal generation
            return {}

    def __del__(self):
        """Cleanup pada object destruction"""
        if self.exchange:
            try:
                asyncio.create_task(self.close())
            except:
                pass
