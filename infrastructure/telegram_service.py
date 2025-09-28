"""
Telegram notification service implementation
Concrete implementation untuk NotificationService
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from domain.entities import TradingSignal, NotificationMessage, SignalType, TrendDirection
from domain.services import NotificationService

logger = logging.getLogger(__name__)

class TelegramService(NotificationService):
    """
    Telegram notification service implementation
    Sends trading signals dan custom messages via Telegram Bot API
    """

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.bot = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialize_bot()

    def _initialize_bot(self) -> None:
        """Initialize Telegram bot instance"""
        try:
            self.bot = Bot(token=self.token)
            self.logger.info("✅ Telegram bot initialized")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Telegram bot: {e}")
            raise

    async def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        try:
            if not self.bot: self._initialize_bot()
            bot_info = await self.bot.get_me()
            self.logger.debug(f"Bot info: @{bot_info.username}")
            return True
        except Exception as e:
            self.logger.error(f"Telegram connection test failed: {e}")
            return False

    async def send_signal_notification(self, signal: TradingSignal) -> bool:
        """Send formatted trading signal notification"""
        try:
            message_content = self._format_signal_message(signal)
            subject = f"PIVOT SUPER-TREND SIGNAL | {signal.symbol}"

            message = NotificationMessage(
                recipient=self.chat_id,
                subject=subject,
                content=message_content,
                timestamp=signal.timestamp,
                message_type=signal.signal_type.value.lower()
            )
            return await self.send_custom_message(message)
        except Exception as e:
            self.logger.error(f"Failed to send signal notification: {e}")
            return False

    async def send_custom_message(self, message: NotificationMessage) -> bool:
        """Send custom formatted message"""
        try:
            if not self.bot: self._initialize_bot()
            message.validate()
            formatted_text = message.format_telegram_message()

            await self.bot.send_message(
                chat_id=message.recipient,
                text=formatted_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=message.disable_web_page_preview
            )
            self.logger.debug(f"📱 Message sent to Telegram: {message.subject}")
            return True
        except TelegramError as e:
            self.logger.error(f"Telegram API error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to send custom message: {e}")
            return False

    async def send_error_notification(
        self, error_message: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send error notification"""
        try:
            content = f"🚨 <b>Error Occurred</b>\n\n<code>{error_message}</code>"
            if context:
                content += "\n\n<b>Context:</b>\n"
                for key, value in context.items():
                    content += f"• <b>{key}:</b> {value}\n"

            error_notification = NotificationMessage(
                recipient=self.chat_id, subject="Bot Error", content=content,
                timestamp=datetime.now(timezone.utc), message_type="error"
            )
            return await self.send_custom_message(error_notification)
        except Exception as e:
            self.logger.error(f"Failed to send error notification: {e}")
            return False

    def _format_signal_message(self, signal: TradingSignal) -> str:
        """Format trading signal into the new, detailed message template."""
        
        signal_icon = "🚀" if signal.signal_type == SignalType.BUY else "🔴"
        trend_icon = "📈" if signal.trend_direction == TrendDirection.BULLISH else "📉"
        
        # Header
        message = f"<b>{signal.symbol} | {signal.timeframe} | {signal.signal_type.value} SIGNAL</b> {signal_icon}\n\n"
        
        # Risk Management Section
        message += "<b>Manajemen Risiko:</b>\n"
        message += f" Zona Entri: <code>${signal.entry_price:,.4f}</code>\n"
        message += f" 🎯 Target Profit: <code>${signal.take_profit:,.4f}</code>\n"
        message += f" 🛡️ Stop Loss: <code>${signal.stop_loss:,.4f}</code>\n\n"
        
        # Analysis Details Section
        message += "<b>Detail Analisis:</b>\n"
        message += f" {trend_icon} Tren Saat Ini: <b>{signal.trend_direction.name}</b>\n"
        message += f" 📊 SuperTrend: <code>${signal.supertrend_value:,.4f}</code>\n"
        if signal.resistance_level:
            message += f" 📈 Resistance: <code>${signal.resistance_level:,.4f}</code>\n"
        if signal.support_level:
            message += f" 📉 Support: <code>${signal.support_level:,.4f}</code>\n"
            
        # Disclaimer
        message += "\n<i>*DYOR. Sinyal ini adalah hasil analisis otomatis.</i>"

        return message

    async def send_test_message(self) -> bool:
        """Send test message to verify connection"""
        try:
            test_message = NotificationMessage(
                recipient=self.chat_id, subject="🧪 Bot Test",
                content="Trading bot test message\n\n✅ Connection working",
                timestamp=datetime.now(timezone.utc), message_type="success"
            )
            return await self.send_custom_message(test_message)
        except Exception as e:
            self.logger.error(f"Failed to send test message: {e}")
            return False

    async def send_startup_notification(self, bot_info: Dict[str, Any]) -> bool:
        """Send bot startup notification"""
        try:
            startup_content = (
                f"🤖 <b>Trading Bot Started</b>\n\n"
                f"🔧 <b>Konfigurasi:</b>\n"
                f"  • Pasangan: {bot_info.get('pairs_count', 0)}\n"
                f"  • Timeframe: {bot_info.get('timeframe', 'N/A')}\n\n"
                f"✅ Bot siap memonitor sinyal..."
            )
            startup_message = NotificationMessage(
                recipient=self.chat_id, subject="Bot Started", content=startup_content,
                timestamp=datetime.now(timezone.utc), message_type="success"
            )
            return await self.send_custom_message(startup_message)
        except Exception as e:
            self.logger.error(f"Failed to send startup notification: {e}")
            return False
