"""
Technical Analysis service implementation using pandas-ta
Implementasi algoritma Pivot Point SuperTrend dari Pine Script ke Python
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Tuple

import pandas_ta as ta

from domain.entities import (
    MarketData, 
    IndicatorData, 
    TradingSignal, 
    AnalysisResult,
    SignalType,
    TrendDirection
)
from domain.services import TradingAnalysisService

logger = logging.getLogger(__name__)

class TechnicalAnalysisService(TradingAnalysisService):
    """
    Technical analysis implementation using pandas-ta
    Converts Pine Script Pivot Point SuperTrend to Python
    """

    def __init__(
        self,
        pivot_period: int = 2,
        atr_factor: float = 3.0,
        atr_period: int = 10,
    ):
        self.pivot_period = pivot_period
        self.atr_factor = atr_factor
        self.atr_period = atr_period
        self.logger = logging.getLogger(self.__class__.__name__)

        # Store previous signals untuk trend change detection
        self.previous_signals: Dict[str, TrendDirection] = {}

    def _market_data_to_dataframe(self, market_data: List[MarketData]) -> pd.DataFrame:
        """Convert MarketData list to pandas DataFrame"""
        data = []
        for md in market_data:
            data.append({
                'timestamp': md.timestamp,
                'open': md.open,
                'high': md.high,
                'low': md.low,
                'close': md.close,
                'volume': md.volume
            })

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        return df
