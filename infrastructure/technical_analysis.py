"""
Technical Analysis service implementation using pandas-ta
Implementasi algoritma Pivot Point SuperTrend dari Pine Script ke Python
"""

import pandas as pd
import logging
from typing import List, Dict, Optional

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
    Implementasi analisis teknis menggunakan pandas-ta dengan konfirmasi multi-timeframe.
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
        self, df: pd.DataFrame, period: int
    ) -> pd.DataFrame:
        """Menghitung pivot points high dan low"""
        df["pivot_high"] = df["high"].rolling(window=period * 2 + 1, center=True).max().shift(period)
        df["pivot_low"] = df["low"].rolling(window=period * 2 + 1, center=True).min().shift(period)
        df["pivot_high"] = df["pivot_high"].bfill()
        df["pivot_low"] = df["pivot_low"].bfill()
        return df

    async def calculate_dynamic_sr(
        self, df: pd.DataFrame
    ) -> Dict[str, Optional[float]]:
        """Menghitung level Support dan Resistance dinamis."""
        recent_pivots = df.tail(50)
        recent_highs = recent_pivots["pivot_high"].dropna().unique()
        recent_lows = recent_pivots["pivot_low"].dropna().unique()
        current_price = df.iloc[-1]["close"]

        resistance = min([p for p in recent_highs if p > current_price], default=None)
        support = max([p for p in recent_lows if p < current_price], default=None)
        
        return {"support": support, "resistance": resistance}

    async def calculate_supertrend(
        self, df: pd.DataFrame, atr_period: int, atr_factor: float
    ) -> pd.DataFrame:
        """Menghitung SuperTrend dan arah tren."""
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
        higher_timeframe_trend: TrendDirection,
    ) -> Optional[TradingSignal]:
        """Menghasilkan sinyal trading yang telah dikonfirmasi oleh tren timeframe lebih tinggi."""
        
        current_price = current_data["close"]
        current_trend_val = current_data["supertrend_direction"]
        prev_trend_val = previous_data["supertrend_direction"]
        primary_trend = TrendDirection.BULLISH if current_trend_val == 1 else TrendDirection.BEARISH
        
        signal_type = None
        # Crossover BUY
        if current_trend_val == 1 and prev_trend_val == -1:
            if higher_timeframe_trend == TrendDirection.BULLISH:
                signal_type = SignalType.BUY
                self.logger.info(f"CONFIRMED BUY signal for {symbol} at {current_price}")
            else:
                self.logger.info(f"IGNORING BUY signal for {symbol}. 1h trend conflicts with 4h trend ({higher_timeframe_trend.name}).")

        # Crossover SELL
        elif current_trend_val == -1 and prev_trend_val == 1:
            if higher_timeframe_trend == TrendDirection.BEARISH:
                signal_type = SignalType.SELL
                self.logger.info(f"CONFIRMED SELL signal for {symbol} at {current_price}")
            else:
                 self.logger.info(f"IGNORING SELL signal for {symbol}. 1h trend conflicts with 4h trend ({higher_timeframe_trend.name}).")
        
        if not signal_type:
            return None

        # Kalkulasi Manajemen Risiko
        risk_reward_ratio = 1.5
        stop_loss = current_data["supertrend"]
        risk = abs(current_price - stop_loss)
        
        if signal_type == SignalType.BUY:
            potential_tp = current_price + (risk * risk_reward_ratio)
            min_tp = current_price + (risk * 0.2) # TP harus setidaknya sedikit di atas entri
            if sr_levels["resistance"] and sr_levels["resistance"] > min_tp:
                 take_profit = min(potential_tp, sr_levels["resistance"])
            else:
                 take_profit = potential_tp
        else: # SELL
            potential_tp = current_price - (risk * risk_reward_ratio)
            min_tp = current_price - (risk * 0.2) # TP harus setidaknya sedikit di bawah entri
            if sr_levels["support"] and sr_levels["support"] < min_tp:
                take_profit = max(potential_tp, sr_levels["support"])
            else:
                take_profit = potential_tp

        # Pastikan TP tidak sama dengan harga entri
        if take_profit == current_price:
            self.logger.warning(f"Take profit is same as entry price for {symbol}. Adjusting using R/R only.")
            if signal_type == SignalType.BUY:
                take_profit = current_price + (risk * risk_reward_ratio)
            else:
                take_profit = current_price - (risk * risk_reward_ratio)


        return TradingSignal(
            symbol=symbol, signal_type=signal_type, timestamp=current_data.name.to_pydatetime(),
            price=current_price, supertrend_value=current_data["supertrend"], trend_direction=primary_trend,
            entry_price=current_price, stop_loss=stop_loss, take_profit=take_profit,
            support_level=sr_levels["support"], resistance_level=sr_levels["resistance"],
            timeframe="1h/4h"
        )

    # REVISI: Tanda tangan fungsi diperbarui untuk menerima data multi-timeframe
    async def analyze_market(
        self,
        symbol: str,
        primary_market_data: List[MarketData],
        higher_market_data: List[MarketData],
        **params,
    ) -> AnalysisResult:
        """Melakukan analisis pasar lengkap menggunakan konfirmasi multi-timeframe."""
        start_time = pd.Timestamp.now()
        
        try:
            # 1. Proses Timeframe Tinggi (4h) untuk menentukan tren utama
            df_higher = self._market_data_to_dataframe(higher_market_data)
            df_higher = await self.calculate_supertrend(df_higher, self.atr_period, self.atr_factor)
            higher_trend_val = df_higher.iloc[-1]["supertrend_direction"]
            higher_timeframe_trend = TrendDirection.BULLISH if higher_trend_val == 1 else TrendDirection.BEARISH

            # 2. Proses Timeframe Utama (1h) untuk sinyal
            df_primary = self._market_data_to_dataframe(primary_market_data)
            df_primary = await self.calculate_pivot_points(df_primary, self.pivot_period)
            df_primary = await self.calculate_supertrend(df_primary, self.atr_period, self.atr_factor)
            
            sr_levels = await self.calculate_dynamic_sr(df_primary)

            latest_data = df_primary.iloc[-1]
            previous_data = df_primary.iloc[-2]

            # 3. Hasilkan sinyal hanya jika dikonfirmasi oleh tren 4 jam
            signal = await self.generate_signal(
                symbol, latest_data, previous_data, sr_levels, higher_timeframe_trend
            )
            
            indicator_data = IndicatorData(
                symbol=symbol, timestamp=latest_data.name.to_pydatetime(),
                supertrend=latest_data.get("supertrend"),
                trend_direction=TrendDirection.BULLISH if latest_data.get("supertrend_direction") == 1 else TrendDirection.BEARISH,
                support_level=sr_levels["support"],
                resistance_level=sr_levels["resistance"],
            )

        except Exception as e:
            self.logger.error(f"Error during analysis for {symbol}: {e}", exc_info=True)
            return AnalysisResult(
                symbol=symbol, timeframe="1h/4h", timestamp=pd.Timestamp.now(tz='UTC'),
                market_data=primary_market_data[-1] if primary_market_data else None,
                indicator_data=None, signal=None,
                analysis_duration_ms=(pd.Timestamp.now() - start_time).total_seconds() * 1000,
            )

        return AnalysisResult(
            symbol=symbol, timeframe="1h/4h", timestamp=pd.Timestamp.now(tz='UTC'),
            market_data=primary_market_data[-1], indicator_data=indicator_data,
            signal=signal,
            analysis_duration_ms=(pd.Timestamp.now() - start_time).total_seconds() * 1000,
        )

