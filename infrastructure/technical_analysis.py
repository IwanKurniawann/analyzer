"""
Technical Analysis service implementation using pandas-ta
Implementasi algoritma Pivot Point SuperTrend dari Pine Script ke Python
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone, timedelta
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
        # Gunakan `shift` untuk memastikan kita hanya melihat data masa lalu
        df["pivot_high"] = df["high"].rolling(window=period * 2 + 1, center=True).max().shift(period)
        df["pivot_low"] = df["low"].rolling(window=period * 2 + 1, center=True).min().shift(period)

        df["pivot_high"] = df["pivot_high"].bfill()
        df["pivot_low"] = df["pivot_low"].bfill()
        return df

    async def calculate_dynamic_sr(
        self, df: pd.DataFrame
    ) -> Dict[str, Optional[float]]:
        """Menghitung level Support dan Resistance dinamis dari pivot points terakhir."""
        recent_pivots = df.tail(50) # Analisis 50 candle terakhir untuk S/R
        
        recent_highs = recent_pivots["pivot_high"].dropna().unique()
        recent_lows = recent_pivots["pivot_low"].dropna().unique()

        current_price = df.iloc[-1]["close"]

        # Resistance adalah pivot high terdekat di atas harga saat ini
        resistance = min([p for p in recent_highs if p > current_price], default=None)
        
        # Support adalah pivot low terdekat di bawah harga saat ini
        support = max([p for p in recent_lows if p < current_price], default=None)
        
        return {"support": support, "resistance": resistance}


    async def calculate_supertrend(
        self,
        df: pd.DataFrame,
        atr_period: int = 10,
        atr_factor: float = 3.0,
    ) -> pd.DataFrame:
        """Menghitung SuperTrend menggunakan pandas-ta"""
        self.logger.debug(
            f"Calculating SuperTrend with ATR period {atr_period} and factor {atr_factor}"
        )
        supertrend_df = df.ta.supertrend(length=atr_period, multiplier=atr_factor)

        df["supertrend"] = supertrend_df[f"SUPERT_{atr_period}_{atr_factor}"]
        df["supertrend_direction"] = supertrend_df[f"SUPERTd_{atr_period}_{atr_factor}"]
        df["atr"] = df.ta.atr(length=atr_period)

        df = df.bfill()
        return df

    async def generate_signal(
        self,
        symbol: str,
        current_data: pd.Series,
        previous_data: pd.Series,
        sr_levels: Dict[str, Optional[float]],
    ) -> Optional[TradingSignal]:
        """Menghasilkan sinyal trading dengan detail TP/SL."""
        
        current_price = current_data["close"]
        current_trend_val = current_data["supertrend_direction"]
        prev_trend_val = previous_data["supertrend_direction"]

        current_trend = (
            TrendDirection.BULLISH if current_trend_val == 1 else TrendDirection.BEARISH
        )
        
        # Deteksi persilangan (crossover) untuk sinyal
        if current_trend_val == 1 and prev_trend_val == -1:
            signal_type = SignalType.BUY
            self.logger.info(f"BUY signal generated for {symbol} at price {current_price}")
        elif current_trend_val == -1 and prev_trend_val == 1:
            signal_type = SignalType.SELL
            self.logger.info(f"SELL signal generated for {symbol} at price {current_price}")
        else:
            return None  # Tidak ada sinyal (HOLD)

        # Kalkulasi Manajemen Risiko
        entry_price = current_price
        stop_loss = None
        take_profit = None
        
        if signal_type == SignalType.BUY:
            # SL di bawah garis supertrend saat ini
            stop_loss = current_data["supertrend"]
            # TP berdasarkan rasio risk/reward 1.5 atau resistance terdekat
            risk = entry_price - stop_loss
            potential_tp = entry_price + (risk * 1.5)
            # Gunakan resistance jika lebih dekat, jika tidak gunakan R/R
            take_profit = min(potential_tp, sr_levels["resistance"]) if sr_levels["resistance"] else potential_tp
            
        elif signal_type == SignalType.SELL:
            # SL di atas garis supertrend saat ini
            stop_loss = current_data["supertrend"]
            # TP berdasarkan rasio risk/reward 1.5 atau support terdekat
            risk = stop_loss - entry_price
            potential_tp = entry_price - (risk * 1.5)
            # Gunakan support jika lebih dekat, jika tidak gunakan R/R
            take_profit = max(potential_tp, sr_levels["support"]) if sr_levels["support"] else potential_tp

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            timestamp=current_data.name.to_pydatetime(),
            price=current_price,
            supertrend_value=current_data["supertrend"],
            trend_direction=current_trend,
            confidence=0.75,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            support_level=sr_levels["support"],
            resistance_level=sr_levels["resistance"],
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
        wib_tz = timezone(timedelta(hours=7))

        try:
            df = self._market_data_to_dataframe(market_data)
            if len(df) < 50: # Memastikan data cukup untuk S/R
                raise ValueError("Data tidak cukup untuk analisis S/R (min 50 baris)")

            df = await self.calculate_pivot_points(df, period=self.pivot_period)
            df = await self.calculate_supertrend(df, atr_period=self.atr_period, atr_factor=self.atr_factor)
            
            # Hitung S/R dinamis
            sr_levels = await self.calculate_dynamic_sr(df)

            latest_data = df.iloc[-1]
            previous_data = df.iloc[-2]

            signal = await self.generate_signal(symbol, latest_data, previous_data, sr_levels)

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
                support_level=sr_levels["support"],
                resistance_level=sr_levels["resistance"],
            )
            
            current_market_data = market_data[-1]

        except Exception as e:
            self.logger.error(f"Error during analysis for {symbol}: {e}", exc_info=True)
            return AnalysisResult(
                symbol=symbol, timeframe=timeframe, timestamp=datetime.now(wib_tz),
                market_data=market_data[-1] if market_data else None,
                indicator_data=None, signal=None,
                analysis_duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

        return AnalysisResult(
            symbol=symbol, timeframe=timeframe, timestamp=datetime.now(wib_tz),
            market_data=current_market_data, indicator_data=indicator_data,
            signal=signal,
            analysis_duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )

