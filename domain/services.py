"""
Domain services - Abstract interfaces untuk business logic
Defines contracts tanpa implementation details
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

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
        """
        Ambil OHLCV data untuk symbol dan timeframe tertentu

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe (e.g., "1h", "4h", "1d") 
            limit: Jumlah data points yang diambil

        Returns:
            List of MarketData objects
        """
        pass

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        """
        Ambil harga terbaru untuk symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest price
        """
        pass

    @abstractmethod
    async def validate_symbol(self, symbol: str) -> bool:
        """
        Validasi apakah symbol tersedia di exchange

        Args:
            symbol: Trading pair symbol

        Returns:
            True if symbol is valid
        """
        pass

class TradingAnalysisService(ABC):
    """Abstract service untuk analisis teknikal"""

    @abstractmethod
    async def calculate_pivot_points(
        self, 
        market_data: List[MarketData],
        period: int = 2
    ) -> Dict[str, List[Optional[float]]]:
        """
        Hitung pivot points dari market data

        Args:
            market_data: List of market data
            period: Pivot period

        Returns:
            Dict containing pivot highs and lows
        """
        pass

    @abstractmethod
    async def calculate_supertrend(
        self,
        market_data: List[MarketData],
        pivot_data: Dict[str, List[Optional[float]]],
        atr_period: int = 10,
        atr_factor: float = 3.0
    ) -> IndicatorData:
        """
        Hitung SuperTrend indicator

        Args:
            market_data: List of market data
            pivot_data: Pivot points data
            atr_period: ATR calculation period
            atr_factor: ATR multiplier factor

        Returns:
            IndicatorData with SuperTrend values
        """
        pass

    @abstractmethod
    async def generate_signal(
        self,
        current_data: MarketData,
        indicator_data: IndicatorData,
        previous_indicator: Optional[IndicatorData] = None
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal berdasarkan indicator data

        Args:
            current_data: Current market data
            indicator_data: Current indicator values
            previous_indicator: Previous indicator values for trend change detection

        Returns:
            TradingSignal if signal detected, None otherwise
        """
        pass

    @abstractmethod
    async def analyze_market(
        self,
        symbol: str,
        timeframe: str,
        **params
    ) -> AnalysisResult:
        """
        Perform complete market analysis

        Args:
            symbol: Trading pair symbol
            timeframe: Analysis timeframe
            **params: Additional parameters

        Returns:
            Complete AnalysisResult
        """
        pass

class NotificationService(ABC):
    """Abstract service untuk mengirim notifikasi"""

    @abstractmethod
    async def send_signal_notification(
        self, 
        signal: TradingSignal
    ) -> bool:
        """
        Kirim notifikasi untuk trading signal

        Args:
            signal: Trading signal to notify

        Returns:
            True if notification sent successfully
        """
        pass

    @abstractmethod
    async def send_custom_message(
        self,
        message: NotificationMessage
    ) -> bool:
        """
        Kirim custom message

        Args:
            message: NotificationMessage object

        Returns:
            True if message sent successfully
        """
        pass

    @abstractmethod
    async def send_error_notification(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Kirim notifikasi error

        Args:
            error_message: Error description
            context: Additional error context

        Returns:
            True if notification sent successfully
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test koneksi ke notification service

        Returns:
            True if connection successful
        """
        pass

class ExchangeService(ABC):
    """Abstract service untuk exchange operations"""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize exchange connection"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close exchange connection"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test exchange connectivity"""
        pass

    @abstractmethod
    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get exchange information and limits"""
        pass
