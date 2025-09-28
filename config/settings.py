"""
Configuration settings untuk trading bot
Menggunakan environment variables dengan fallback defaults
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables dari .env file (untuk development)
load_dotenv()

class Settings:
    """Centralized configuration management"""

    # KuCoin API Configuration
    KUCOIN_API_KEY: str = os.getenv("KUCOIN_API_KEY", "")
    KUCOIN_API_SECRET: str = os.getenv("KUCOIN_API_SECRET", "")
    KUCOIN_PASSPHRASE: str = os.getenv("KUCOIN_PASSPHRASE", "")
    # Menghapus KUCOIN_SANDBOX

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Trading Parameters
    TRADING_PAIRS: List[str] = os.getenv(
        "TRADING_PAIRS", 
        "BTC/USDT,ETH/USDT,SOL/USDT,ADA/USDT,MATIC/USDT"
    ).split(",")

    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")
    PIVOT_PERIOD: int = int(os.getenv("PIVOT_PERIOD", "2"))
    ATR_FACTOR: float = float(os.getenv("ATR_FACTOR", "3.0"))
    ATR_PERIOD: int = int(os.getenv("ATR_PERIOD", "10"))

    # Data Parameters
    OHLCV_LIMIT: int = int(os.getenv("OHLCV_LIMIT", "100"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Notification Settings
    SEND_TEST_MESSAGE: bool = os.getenv("SEND_TEST_MESSAGE", "False").lower() == "true"
    ENABLE_NOTIFICATIONS: bool = os.getenv("ENABLE_NOTIFICATIONS", "True").lower() == "true"

    def __init__(self):
        """Validate required settings on initialization"""
        self._validate_required_settings()

    def _validate_required_settings(self) -> None:
        """Validate that required environment variables are set"""
        required_settings = [
            ("KUCOIN_API_KEY", self.KUCOIN_API_KEY),
            ("KUCOIN_API_SECRET", self.KUCOIN_API_SECRET), 
            ("KUCOIN_PASSPHRASE", self.KUCOIN_PASSPHRASE),
            ("TELEGRAM_BOT_TOKEN", self.TELEGRAM_BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", self.TELEGRAM_CHAT_ID),
        ]

        missing_settings = []
        for setting_name, setting_value in required_settings:
            if not setting_value or setting_value.strip() == "":
                missing_settings.append(setting_name)

        if missing_settings:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_settings)}\n"
                f"Please set these variables in GitHub Secrets or .env file"
            )

    def get_kucoin_config(self) -> dict:
        """Get KuCoin exchange configuration"""
        return {
            "apiKey": self.KUCOIN_API_KEY,
            "secret": self.KUCOIN_API_SECRET,
            "password": self.KUCOIN_PASSPHRASE,
            "enableRateLimit": True,
            "timeout": 30000,
        }

    def get_trading_config(self) -> dict:
        """Get trading parameters configuration"""
        return {
            "pairs": self.TRADING_PAIRS,
            "timeframe": self.TIMEFRAME,
            "pivot_period": self.PIVOT_PERIOD,
            "atr_factor": self.ATR_FACTOR,
            "atr_period": self.ATR_PERIOD,
            "ohlcv_limit": self.OHLCV_LIMIT,
        }

    def __repr__(self) -> str:
        """String representation (safe - no secrets)"""
        return (
            f"Settings("
            f"pairs={len(self.TRADING_PAIRS)}, "
            f"timeframe='{self.TIMEFRAME}', "
            f"pivot_period={self.PIVOT_PERIOD}, "
            f"atr_factor={self.ATR_FACTOR}"
            f")"
        )
