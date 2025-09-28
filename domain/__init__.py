"""
Domain layer - Core business logic, entities, and service interfaces.
This layer should have no dependencies on other layers.
"""

from .entities import (
    MarketData,
    IndicatorData,
    TradingSignal,
    NotificationMessage,
    AnalysisResult,
    SignalType,
    TrendDirection,
)
from .services import (
    MarketDataService,
    TradingAnalysisService,
    NotificationService,
    ExchangeService,
)

__all__ = [
    # Entities
    "MarketData",
    "IndicatorData",
    "TradingSignal",
    "NotificationMessage",
    "AnalysisResult",
    "SignalType",
    "TrendDirection",
    # Services (Abstract Interfaces)
    "MarketDataService",
    "TradingAnalysisService",
    "NotificationService",
    "ExchangeService",
]
