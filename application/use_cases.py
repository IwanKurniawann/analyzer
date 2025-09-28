"""
Use cases - Application business logic
Orchestrates domain services dan infrastructure services
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any

from domain.entities import AnalysisResult, TradingSignal
from domain.services import (
    MarketDataService, 
    TradingAnalysisService, 
    NotificationService, 
    ExchangeService
)

logger = logging.getLogger(__name__)

class TradingUseCase:
    """
    Use case utama untuk analisis trading dan notifikasi
    Mengkoordinasikan semua layanan untuk alur kerja trading yang lengkap
    """

    def __init__(
        self,
        exchange: MarketDataService and ExchangeService,
        telegram_service: NotificationService,
        technical_analysis: TradingAnalysisService,
        settings: Any,
    ):
        self.exchange = exchange
        self.telegram_service = telegram_service
        self.technical_analysis = technical_analysis
        self.settings = settings
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize_services(self) -> None:
        """Inisialisasi layanan eksternal"""
        self.logger.info("🔌 Initializing external services...")
        await self.exchange.initialize()
        self.logger.info("✅ All services initialized successfully.")

    async def shutdown_services(self) -> None:
        """Mematikan layanan eksternal"""
        self.logger.info("🔌 Shutting down external services...")
        await self.exchange.close()
        self.logger.info("✅ All services shut down successfully.")

    async def analyze_and_notify(self) -> Dict[str, Any]:
        """
        Alur kerja utama: menganalisis semua pasangan trading dan mengirim notifikasi
        """
        start_time = datetime.now()
        self.logger.info("🔍 Starting trading analysis")

        results = {
            "timestamp": start_time.isoformat(),
            "pairs_analyzed": 0,
            "signals_generated": 0,
            "errors": [],
        }

        try:
            await self._test_connections()

            tasks = [self._analyze_and_notify_single_pair(pair.strip()) for pair in self.settings.TRADING_PAIRS]
            analysis_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Titik pusat penanganan kesalahan untuk semua pasangan
            for i, result in enumerate(analysis_results):
                pair = self.settings.TRADING_PAIRS[i].strip()
                if isinstance(result, Exception):
                    error_msg = f"Error processing {pair}: {result}"
                    self.logger.error(error_msg, exc_info=False) # Cukup log pesan, traceback sudah ditangkap
                    results["errors"].append(error_msg)
                    await self._send_error_notification(pair, str(result))
                elif result and result.has_signal():
                    results["signals_generated"] += 1
                if not isinstance(result, Exception):
                    results["pairs_analyzed"] += 1
        
        except Exception as e:
            error_msg = f"Critical error in trading analysis: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)
            await self._send_critical_error_notification(str(e))
        
        finally:
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.info(
                f"✅ Analysis completed: {results['pairs_analyzed']} pairs, "
                f"{results['signals_generated']} signals ({execution_time:.2f}s)"
            )
            return results

    async def _analyze_and_notify_single_pair(self, pair: str) -> Optional[AnalysisResult]:
        """
        Menganalisis dan memberitahu untuk satu pasangan.
        REVISI: Blok try-except dihapus untuk sentralisasi penanganan error.
        """
        self.logger.info(f"📊 Analyzing {pair}")
        
        analysis_result = await self._analyze_single_pair(pair)

        if analysis_result and analysis_result.has_signal():
            self.logger.info(
                f"🚨 {analysis_result.signal.signal_type.value} SIGNAL: "
                f"{pair} @ {analysis_result.signal.price:.4f}"
            )
            await self._send_signal_notification(analysis_result.signal)
        elif analysis_result:
            self.logger.info(f"➡️ {pair}: No signal (HOLD)")
        
        return analysis_result

    async def _analyze_single_pair(self, symbol: str) -> Optional[AnalysisResult]:
        """Menganalisis satu pasangan trading dengan konfirmasi multi-timeframe"""
        
        primary_data_task = self.exchange.get_ohlcv_data(
            symbol=symbol,
            timeframe=self.settings.PRIMARY_TIMEFRAME,
            limit=self.settings.OHLCV_LIMIT
        )
        higher_data_task = self.exchange.get_ohlcv_data(
            symbol=symbol,
            timeframe=self.settings.HIGHER_TIMEFRAME,
            limit=self.settings.OHLCV_LIMIT
        )
        
        primary_market_data, higher_market_data = await asyncio.gather(primary_data_task, higher_data_task)

        if not primary_market_data or len(primary_market_data) < 50:
            raise ValueError(f"Insufficient primary timeframe data for {symbol}")
        if not higher_market_data or len(higher_market_data) < 20:
            raise ValueError(f"Insufficient higher timeframe data for {symbol}")

        analysis_result = await self.technical_analysis.analyze_market(
            symbol=symbol,
            primary_market_data=primary_market_data,
            higher_market_data=higher_market_data
        )
        return analysis_result

    async def _test_connections(self) -> None:
        """Tes koneksi ke layanan eksternal"""
        self.logger.info("🔗 Testing service connections")
        if not await self.exchange.test_connection():
            raise ConnectionError("Exchange connection test failed")
        self.logger.info("✅ Exchange connection OK")

        if not await self.telegram_service.test_connection():
            raise ConnectionError("Telegram connection test failed")
        self.logger.info("✅ Telegram connection OK")

    async def _send_signal_notification(self, signal: TradingSignal) -> None:
        """Mengirim notifikasi sinyal trading"""
        if self.settings.ENABLE_NOTIFICATIONS:
            await self.telegram_service.send_signal_notification(signal)

    async def _send_error_notification(self, symbol: str, error: str) -> None:
        """Mengirim notifikasi error untuk pasangan tertentu"""
        if self.settings.ENABLE_NOTIFICATIONS:
            await self.telegram_service.send_error_notification(
                f"Error analyzing {symbol}: {error}"
            )

    async def _send_critical_error_notification(self, error: str) -> None:
        """Mengirim notifikasi error kritis"""
        if self.settings.ENABLE_NOTIFICATIONS:
            await self.telegram_service.send_error_notification(
                f"Critical bot error: {error}"
            )

