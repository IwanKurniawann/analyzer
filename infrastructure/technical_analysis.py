"""
Technical Analysis service implementation using pandas-ta
Implementasi algoritma Pivot Point SuperTrend dari Pine Script ke Python
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

import pandas_ta as ta

from domain.entities import (
    MarketData,
    IndicatorData,
    TradingSignal,
    AnalysisResult,
    SignalType,
    TrendDirection,
)
from domain.services import TradingAnalysisService

logger = logging.getLogger(__name__)


class TechnicalAnalysisService(TradingAnalysisService):
    """
    Implementasi analisis teknis menggunakan pandas-ta
    Mengonversi logika Pivot Point SuperTrend dari Pine Script ke Python
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
        # Simpan state tren sebelumnya untuk deteksi persilangan
        self.previous_trend: Dict[str, TrendDirection] = {}

    def _market_data_to_dataframe(self, market_data: List[MarketData]) -> pd.DataFrame:
        """Mengonversi daftar MarketData menjadi pandas DataFrame"""
        data = [
            {
                "timestamp": md.timestamp,
                "open": md.open,
                "high": md.high,
                "low": md.low,
                "close": md.close,
                "volume": md.volume,
            }
            for md in market_data
        ]
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df

    async def calculate_pivot_points(
        self, df: pd.DataFrame, period: int = 2
    ) -> pd.DataFrame:
        """Menghitung pivot points high dan low"""
        self.logger.debug(f"Calculating pivot points with period {period}")
        df["pivot_high"] = df["high"].rolling(window=period * 2 + 1, center=True).max()
        df["pivot_low"] = df["low"].rolling(window=period * 2 + 1, center=True).min()
        
        # REVISI: Menggunakan metode modern dan aman untuk mengisi nilai NaN
        # Menghindari ChainedAssignmentError dan FutureWarning
        df["pivot_high"] = df["pivot_high"].bfill()
        df["pivot_low"] = df["pivot_low"].bfill()
        return df

    async def calculate_supertrend(
        self,
        df: pd.DataFrame,
        atr_period: int = 10,
        atr_factor: float = 3.0,
    ) -> pd.DataFrame:
        """Menghitung SuperTrend menggunakan pandas-ta"""
        self.logger.debug(f"Calculating SuperTrend with ATR period {atr_period} and factor {atr_factor}")
        supertrend_df = df.ta.supertrend(
            length=atr_period, multiplier=atr_factor
        )
        
        # Menggabungkan hasil supertrend ke DataFrame utama
        df["supertrend"] = supertrend_df[f"SUPERT_{atr_period}_{atr_factor}"]
        df["supertrend_direction"] = supertrend_df[f"SUPERTd_{atr_period}_{atr_factor}"]
        df["atr"] = df.ta.atr(length=atr_period) # Hitung ATR secara terpisah untuk data tambahan
        
        # REVISI: Menggunakan metode modern untuk mengisi nilai NaN di seluruh DataFrame
        df = df.bfill()
        return df

    async def generate_signal(
        self,
        symbol: str,
        current_data: pd.Series,
        previous_data: pd.Series,
    ) -> Optional[TradingSignal]:
        """Menghasilkan sinyal trading berdasarkan perubahan tren SuperTrend"""
        
        current_price = current_data["close"]
        current_trend_val = current_data["supertrend_direction"]
        prev_trend_val = previous_data["supertrend_direction"]

        current_trend = TrendDirection.BULLISH if current_trend_val == 1 else TrendDirection.BEARISH
        
        # Simpan tren saat ini untuk perbandingan berikutnya
        self.previous_trend[symbol] = current_trend

        # Deteksi persilangan (crossover)
        if current_trend_val == 1 and prev_trend_val == -1:
            signal_type = SignalType.BUY
            self.logger.info(f"BUY signal generated for {symbol} at price {current_price}")
        elif current_trend_val == -1 and prev_trend_val == 1:
            signal_type = SignalType.SELL
            self.logger.info(f"SELL signal generated for {symbol} at price {current_price}")
        else:
            return None # Tidak ada sinyal (HOLD)

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            timestamp=current_data.name.to_pydatetime(),
            price=current_price,
            supertrend_value=current_data["supertrend"],
            trend_direction=current_trend,
            confidence=0.70, # Contoh nilai kepercayaan
            stop_loss=current_data["supertrend"] if signal_type == SignalType.BUY else None,
            take_profit=None,
        )

    async def analyze_market(
        self,
        symbol: str,
        timeframe: str,
        market_data: List[MarketData],
        **params,
    ) -> AnalysisResult:
        """Melakukan analisis pasar lengkap untuk satu pasangan trading"""
        start_time = datetime.now()
        
        try:
            df = self._market_data_to_dataframe(market_data)
            
            # 1. Hitung Pivot Points
            df = await self.calculate_pivot_points(df, period=self.pivot_period)
            
            # 2. Hitung SuperTrend
            df = await self.calculate_supertrend(df, atr_period=self.atr_period, atr_factor=self.atr_factor)

            # Ambil data terbaru dan data sebelumnya
            if len(df) < 2:
                raise ValueError("Data tidak cukup untuk analisis (membutuhkan setidaknya 2 baris)")
                
            latest_data = df.iloc[-1]
            previous_data = df.iloc[-2]

            # 3. Hasilkan Sinyal
            signal = await self.generate_signal(symbol, latest_data, previous_data)
            
            # Siapkan data indikator untuk hasil
            indicator_data = IndicatorData(
                symbol=symbol,
                timestamp=latest_data.name.to_pydatetime(),
                pivot_high=latest_data.get("pivot_high"),
                pivot_low=latest_data.get("pivot_low"),
                supertrend=latest_data.get("supertrend"),
                atr=latest_data.get("atr"),
                trend_direction=(
                    TrendDirection.BULLISH if latest_data.get("supertrend_direction") == 1 
                    else TrendDirection.BEARISH
                ),
            )
            
            current_market_data = market_data[-1]

        except Exception as e:
            self.logger.error(f"Error during analysis for {symbol}: {e}", exc_info=True)
            return AnalysisResult(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.now(timezone.utc),
                market_data=market_data[-1] if market_data else None,
                indicator_data=None,
                signal=None,
                analysis_duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )
        return AnalysisResult(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(timezone.utc + timedelta(hours=7))   ,
            market_data=current_market_data,
            indicator_data=indicator_data,
            signal=signal,
            analysis_duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )
