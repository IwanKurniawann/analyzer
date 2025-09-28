#!/usr/bin/env python3
"""
Pivot Point SuperTrend Trading Bot
Entry point untuk aplikasi trading bot dengan clean architecture
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from config.settings import Settings
from application.use_cases import TradingUseCase
from infrastructure.exchanges import KuCoinExchange
from infrastructure.telegram_service import TelegramService
from infrastructure.technical_analysis import TechnicalAnalysisService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('trading_bot.log')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """Main application entry point"""
    try:
        # Load configuration
        settings = Settings()
        logger.info("🚀 Trading bot started")

        # Initialize services (Dependency Injection)
        exchange = KuCoinExchange(
            api_key=settings.KUCOIN_API_KEY,
            api_secret=settings.KUCOIN_API_SECRET,
            passphrase=settings.KUCOIN_PASSPHRASE,
            sandbox=settings.KUCOIN_SANDBOX
        )

        telegram_service = TelegramService(
            token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=settings.TELEGRAM_CHAT_ID
        )

        technical_analysis = TechnicalAnalysisService(
            pivot_period=settings.PIVOT_PERIOD,
            atr_factor=settings.ATR_FACTOR,
            atr_period=settings.ATR_PERIOD
        )

        # Initialize use case
        trading_use_case = TradingUseCase(
            exchange=exchange,
            telegram_service=telegram_service,
            technical_analysis=technical_analysis,
            settings=settings
        )

        # Execute trading analysis
        await trading_use_case.analyze_and_notify()

        logger.info("✅ Trading analysis completed successfully")

    except Exception as e:
        logger.error(f"❌ Application error: {e}", exc_info=True)
        # Send error notification to Telegram
        try:
            error_telegram = TelegramService(
                token=Settings().TELEGRAM_BOT_TOKEN,
                chat_id=Settings().TELEGRAM_CHAT_ID
            )
            await error_telegram.send_message(f"🚨 Bot Error: {str(e)}")
        except:
            pass
        sys.exit(1)

    finally:
        logger.info("🔄 Trading bot shutdown")

if __name__ == "__main__":
    asyncio.run(main())
