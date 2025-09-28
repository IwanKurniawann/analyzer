"""
Configuration settings untuk trading bot
Menggunakan environment variables dengan fallback defaults
"""

import os
from typing import List

class Settings:
    """Manajemen konfigurasi terpusat"""

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Proxy Configuration (Opsional, untuk lingkungan seperti GitHub Actions)
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", "")
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "")

    # Trading Parameters
    TRADING_PAIRS: List[str] = os.getenv(
        "TRADING_PAIRS",
        "BTC/USDT,ETH/USDT,XRP/USDT,LTC/USDT,BCH/USDT,ADA/USDT,LINK/USDT,BNB/USDT,EOS/USDT,XTZ/USDT"
    ).split(",")

    # REVISI: Menambahkan timeframe yang lebih tinggi untuk konfirmasi tren
    PRIMARY_TIMEFRAME: str = os.getenv("PRIMARY_TIMEFRAME", "1h")
    HIGHER_TIMEFRAME: str = os.getenv("HIGHER_TIMEFRAME", "4h")

    PIVOT_PERIOD: int = int(os.getenv("PIVOT_PERIOD", "2"))
    ATR_FACTOR: float = float(os.getenv("ATR_FACTOR", "3.0"))
    ATR_PERIOD: int = int(os.getenv("ATR_PERIOD", "10"))

    # Data Parameters
    OHLCV_LIMIT: int = int(os.getenv("OHLCV_LIMIT", "200"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Notification Settings
    ENABLE_NOTIFICATIONS: bool = os.getenv("ENABLE_NOTIFICATIONS", "True").lower() == "true"

    def __init__(self):
        """Validasi pengaturan yang diperlukan saat inisialisasi"""
        self._validate_required_settings()

    def _validate_required_settings(self) -> None:
        """Validasi bahwa variabel lingkungan yang diperlukan sudah diatur"""
        required_settings = [
            ("TELEGRAM_BOT_TOKEN", self.TELEGRAM_BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", self.TELEGRAM_CHAT_ID),
        ]

        missing_settings = [name for name, value in required_settings if not value or not value.strip()]

        if missing_settings:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_settings)}\n"
                f"Please set these variables in GitHub Secrets or .env file"
            )

    def get_proxy_config(self) -> dict:
        """Mendapatkan konfigurasi proxy jika tersedia"""
        proxies = {}
        if self.HTTP_PROXY:
            proxies['http'] = self.HTTP_PROXY
        if self.HTTPS_PROXY:
            proxies['https'] = self.HTTPS_PROXY
        return proxies

