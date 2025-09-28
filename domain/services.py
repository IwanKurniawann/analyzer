"""
Domain services - Abstract interfaces untuk business logic
Defines contracts tanpa implementation details
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from .entities import (
    MarketData,
    TradingSignal, 
    IndicatorData,
    NotificationMessage,
    AnalysisResult,
)

class MarketDataService(ABC):
    """Abstract service untuk mengambil market data"""

    @abstractmethod
    async def get_ohlcv_data(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[MarketData]:
        pass

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    async def validate_symbol(self, symbol: str) -> bool:
        pass

class TradingAnalysisService(ABC):
    """Abstract service untuk analisis teknikal"""

    @abstractmethod
    async def calculate_pivot_points(self, df, period: int = 2):
        pass
    
    @abstractmethod
    async def calculate_supertrend(self, df, atr_period: int = 10, atr_factor: float = 3.0):
        pass

    @abstractmethod
    async def generate_signal(self, symbol, current_data, previous_data, sr_levels, higher_timeframe_trend):
        pass
    
    # REVISI: Memperbarui definisi fungsi untuk mendukung multi-timeframe
    @abstractmethod
    async def analyze_market(
        self,
        symbol: str,
        primary_market_data: List[MarketData],
        higher_market_data: List[MarketData],
        **params,
    ) -> AnalysisResult:
        """
        Perform complete market analysis using multi-timeframe confirmation.

        Args:
            symbol: Trading pair symbol
            primary_market_data: OHLCV data for the primary (e.g., 1h) timeframe.
            higher_market_data: OHLCV data for the higher (e.g., 4h) timeframe.
            **params: Additional parameters for analysis.

        Returns:
            Complete AnalysisResult.
        """
        pass


class NotificationService(ABC):
    """Abstract service untuk mengirim notifikasi"""

    @abstractmethod
    async def send_signal_notification(
        self, 
        signal: TradingSignal
    ) -> bool:
        pass

    @abstractmethod
    async def send_custom_message(
        self,
        message: NotificationMessage
    ) -> bool:
        pass

    @abstractmethod
    async def send_error_notification(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        pass


class ExchangeService(ABC):
    """Abstract service untuk exchange operations"""

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    async def get_exchange_info(self) -> Dict[str, Any]:
        pass

