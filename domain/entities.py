"""
Domain entities - Core business objects
Tidak memiliki dependencies ke layer lain
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class TrendDirection(Enum):
    """Trend direction"""
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0

@dataclass
class MarketData:
    """Market data entity containing OHLCV information"""
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        """Validate market data after initialization"""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than Low ({self.low})")
        if self.open <= 0 or self.close <= 0:
            raise ValueError("Open and Close prices must be positive")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")

@dataclass
class IndicatorData:
    """Technical indicator calculation results"""
    symbol: str
    timestamp: datetime

    # Pivot Points
    pivot_high: Optional[float] = None
    pivot_low: Optional[float] = None
    center_line: Optional[float] = None

    # SuperTrend
    atr: Optional[float] = None
    upper_band: Optional[float] = None
    lower_band: Optional[float] = None
    supertrend: Optional[float] = None
    trend_direction: TrendDirection = TrendDirection.NEUTRAL

    # Support/Resistance
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None

    def is_valid(self) -> bool:
        """Check if indicator data is valid for signal generation"""
        required_fields = [
            self.center_line,
            self.atr,
            self.supertrend,
        ]
        return all(field is not None for field in required_fields)

@dataclass
class TradingSignal:
    """Trading signal entity"""
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    supertrend_value: float
    trend_direction: TrendDirection
    confidence: float = 0.0

    # Risk Management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Additional Context
    timeframe: str = "1h"
    indicator_values: Optional[Dict[str, float]] = None

    def __post_init__(self):
        """Validate signal data"""
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("Confidence must be between 0 and 1")
        if self.price <= 0:
            raise ValueError("Price must be positive")

        # Validate stop loss and take profit
        if self.signal_type == SignalType.BUY:
            if self.stop_loss and self.stop_loss >= self.price:
                raise ValueError("Buy signal: stop loss must be below entry price")
            if self.take_profit and self.take_profit <= self.price:
                raise ValueError("Buy signal: take profit must be above entry price")
        elif self.signal_type == SignalType.SELL:
            if self.stop_loss and self.stop_loss <= self.price:
                raise ValueError("Sell signal: stop loss must be above entry price")  
            if self.take_profit and self.take_profit >= self.price:
                raise ValueError("Sell signal: take profit must be below entry price")

    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary for serialization"""
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "supertrend_value": self.supertrend_value,
            "trend_direction": self.trend_direction.value,
            "confidence": self.confidence,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "timeframe": self.timeframe,
            "indicator_values": self.indicator_values,
        }

@dataclass
class NotificationMessage:
    """Notification message entity"""
    recipient: str
    subject: str
    content: str
    timestamp: datetime
    message_type: str = "info"  # info, warning, error, success

    # Telegram specific
    parse_mode: str = "HTML"
    disable_web_page_preview: bool = True

    def format_telegram_message(self) -> str:
        """Format message for Telegram with HTML formatting"""
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️", 
            "error": "❌",
            "success": "✅",
            "buy": "🚀",
            "sell": "🔴",
        }

        emoji = emoji_map.get(self.message_type.lower(), "📊")

        formatted_message = f"{emoji} <b>{self.subject}</b>\n\n{self.content}"

        # Add timestamp
        time_str = self.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        formatted_message += f"\n\n⏰ <i>{time_str}</i>"

        return formatted_message

    def validate(self) -> None:
        """Validate notification message"""
        if not self.recipient or not self.recipient.strip():
            raise ValueError("Recipient cannot be empty")
        if not self.content or not self.content.strip():
            raise ValueError("Content cannot be empty")
        if len(self.content) > 4096:  # Telegram message limit
            raise ValueError("Content exceeds Telegram message limit (4096 characters)")

@dataclass
class AnalysisResult:
    """Complete analysis result for a trading pair"""
    symbol: str
    timeframe: str
    timestamp: datetime
    market_data: MarketData
    indicator_data: IndicatorData
    signal: Optional[TradingSignal] = None
    analysis_duration_ms: float = 0.0

    def has_signal(self) -> bool:
        """Check if analysis generated a trading signal"""
        return (
            self.signal is not None and 
            self.signal.signal_type in [SignalType.BUY, SignalType.SELL]
        )

    def is_successful(self) -> bool:
        """Check if analysis completed successfully"""
        return (
            self.market_data is not None and
            self.indicator_data is not None and
            self.indicator_data.is_valid()
        )
