"""
Telegram notification service implementation
Concrete implementation untuk NotificationService
"""

import asyncio
import logging
from datetime import datetime, timezone
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

        # Initialize bot
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
            if not self.bot:
                self._initialize_bot()

            # Test by getting bot info
            bot_info = await self.bot.get_me()
            self.logger.debug(f"Bot info: @{bot_info.username}")
            return True

        except Exception as e:
            self.logger.error(f"Telegram connection test failed: {e}")
            return False

    async def send_signal_notification(self, signal: TradingSignal) -> bool:
        """
        Send formatted trading signal notification

        Args:
            signal: TradingSignal to send

        Returns:
            True if message sent successfully
        """
        try:
            message_content = self._format_signal_message(signal)

            message = NotificationMessage(
                recipient=self.chat_id,
                subject=f"{signal.signal_type.value} Signal",
                content=message_content,
                timestamp=signal.timestamp,
                message_type=signal.signal_type.value.lower()
            )

            return await self.send_custom_message(message)

        except Exception as e:
            self.logger.error(f"Failed to send signal notification: {e}")
            return False

    async def send_custom_message(self, message: NotificationMessage) -> bool:
        """
        Send custom formatted message

        Args:
            message: NotificationMessage to send

        Returns:
            True if message sent successfully
        """
        try:
            if not self.bot:
                self._initialize_bot()

            # Validate message
            message.validate()

            # Format message untuk Telegram
            formatted_text = message.format_telegram_message()

            # Send message
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
        self, 
        error_message: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send error notification

        Args:
            error_message: Error description
            context: Additional error context

        Returns:
            True if notification sent successfully
        """
        try:
            content = f"🚨 <b>Error Occurred</b>\n\n"
            content += f"<code>{error_message}</code>"

            if context:
                content += "\n\n<b>Context:</b>\n"
                for key, value in context.items():
                    content += f"• <b>{key}:</b> {value}\n"

            error_notification = NotificationMessage(
                recipient=self.chat_id,
                subject="Bot Error",
                content=content,
                timestamp=datetime.now(timezone.utc),
                message_type="error"
            )

            return await self.send_custom_message(error_notification)

        except Exception as e:
            self.logger.error(f"Failed to send error notification: {e}")
            return False

    def _format_signal_message(self, signal: TradingSignal) -> str:
        """
        Format trading signal into readable message

        Args:
            signal: TradingSignal to format

        Returns:
            Formatted message string
        """
        # Emoji mappings
        signal_emoji = {
            SignalType.BUY: "🚀",
            SignalType.SELL: "🔴", 
            SignalType.HOLD: "➡️"
        }

        trend_emoji = {
            TrendDirection.BULLISH: "📈",
            TrendDirection.BEARISH: "📉",
            TrendDirection.NEUTRAL: "➡️"
        }

        # Get emojis
        signal_icon = signal_emoji.get(signal.signal_type, "📊")
        trend_icon = trend_emoji.get(signal.trend_direction, "➡️")

        # Build message
        message = f"{signal_icon} <b>{signal.signal_type.value} SIGNAL</b>\n\n"

        # Trading pair and timeframe
        message += f"💎 <b>Pair:</b> {signal.symbol} ({signal.timeframe})\n"

        # Price information
        message += f"💰 <b>Price:</b> ${signal.price:,.4f}\n"
        message += f"📊 <b>SuperTrend:</b> ${signal.supertrend_value:,.4f}\n"

        # Trend information
        trend_name = signal.trend_direction.name
        message += f"{trend_icon} <b>Trend:</b> {trend_name}\n"

        # Confidence if available
        if signal.confidence > 0:
            confidence_percent = signal.confidence * 100
            message += f"🎯 <b>Confidence:</b> {confidence_percent:.1f}%\n"

        # Risk management levels
        if signal.stop_loss:
            message += f"🛡️ <b>Stop Loss:</b> ${signal.stop_loss:,.4f}\n"
        if signal.take_profit:
            message += f"🎯 <b>Take Profit:</b> ${signal.take_profit:,.4f}\n"

        # Additional indicator values
        if signal.indicator_values:
            message += "\n<b>📈 Indicators:</b>\n"
            for key, value in signal.indicator_values.items():
                if isinstance(value, float):
                    message += f"• {key}: {value:.4f}\n"
                else:
                    message += f"• {key}: {value}\n"

        # Timestamp
        time_str = signal.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        message += f"\n⏰ {time_str}"

        # Add trading advice based on signal type
        if signal.signal_type == SignalType.BUY:
            message += "\n\n💡 <i>Consider buying position above SuperTrend level</i>"
        elif signal.signal_type == SignalType.SELL:
            message += "\n\n💡 <i>Consider selling position below SuperTrend level</i>"

        return message

    async def send_test_message(self) -> bool:
        """
        Send test message to verify connection

        Returns:
            True if test message sent successfully
        """
        try:
            test_message = NotificationMessage(
                recipient=self.chat_id,
                subject="🧪 Bot Test",
                content=(
                    "Trading bot test message\n\n"
                    "✅ Telegram connection working\n"
                    "✅ Message formatting OK\n"
                    "✅ Ready to send trading signals"
                ),
                timestamp=datetime.now(timezone.utc),
                message_type="success"
            )

            return await self.send_custom_message(test_message)

        except Exception as e:
            self.logger.error(f"Failed to send test message: {e}")
            return False

    async def send_startup_notification(self, bot_info: Dict[str, Any]) -> bool:
        """
        Send bot startup notification

        Args:
            bot_info: Bot configuration information

        Returns:
            True if notification sent successfully
        """
        try:
            startup_content = (
                f"🤖 <b>Trading Bot Started</b>\n\n"
                f"🔧 <b>Configuration:</b>\n"
                f"• Pairs: {bot_info.get('pairs_count', 0)}\n"
                f"• Timeframe: {bot_info.get('timeframe', 'N/A')}\n"
                f"• Pivot Period: {bot_info.get('pivot_period', 'N/A')}\n"
                f"• ATR Factor: {bot_info.get('atr_factor', 'N/A')}\n\n"
                f"✅ All systems ready\n"
                f"🎯 Monitoring for signals..."
            )

            startup_message = NotificationMessage(
                recipient=self.chat_id,
                subject="Bot Started",
                content=startup_content,
                timestamp=datetime.now(timezone.utc),
                message_type="success"
            )

            return await self.send_custom_message(startup_message)

        except Exception as e:
            self.logger.error(f"Failed to send startup notification: {e}")
            return False
