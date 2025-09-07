# -*- coding: utf-8 -*-

"""
Skrip utama untuk menganalisis data harga BTC/USDT dari Binance,
menghasilkan sinyal perdagangan berdasarkan strategi Multi-Timeframe (Top-Down),
dan mengirim notifikasi ke Telegram.

Versi ini menambahkan deteksi pola candlestick sebagai konfirmasi akhir.
"""

import os
import sys
import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import telegram

# --- KONFIGURASI ---
SYMBOL = 'BTC/USDT'
TREND_TIMEFRAME = '1d'
SIGNAL_TIMEFRAME = '4h'
LIMIT = 250

# Pengaturan Indikator
SMA_SHORT_PERIOD = 50
SMA_LONG_PERIOD = 200
RSI_PERIOD = 14
RSI_CONFIRMATION_LEVEL = 50
TREND_SMA_PERIOD = 200

LAST_SIGNAL_FILE = "last_signal.txt"

# --- KREDENSIAL (diambil dari GitHub Secrets) ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def check_credentials():
    """Memeriksa apakah kredensial Telegram sudah diatur."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur di GitHub Secrets.")
        sys.exit(1)

def fetch_data(symbol, timeframe, limit):
    """Mengambil data OHLCV dari Binance menggunakan ccxt."""
    try:
        print(f"Mengambil {limit} data candle terakhir untuk {symbol} pada timeframe {timeframe}...")
        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print("Data berhasil diambil.")
        return df
    except Exception as e:
        print(f"Error saat mengambil data dari Binance: {e}")
        return None

def calculate_indicators(df, sma_short=None, sma_long=None, rsi=None, trend_sma=None, patterns=False):
    """
    Menghitung indikator teknis dan pola candlestick yang dibutuhkan.
    """
    print(f"Menghitung indikator teknis...")
    if sma_short and sma_long:
        df[f'SMA_{sma_short}'] = ta.sma(df['close'], length=sma_short)
        df[f'SMA_{sma_long}'] = ta.sma(df['close'], length=sma_long)
    if rsi:
        df[f'RSI_{rsi}'] = ta.rsi(df['close'], length=rsi)
    if trend_sma:
        df[f'SMA_{trend_sma}'] = ta.sma(df['close'], length=trend_sma)
    
    # --- BARU: Deteksi Pola Candlestick ---
    if patterns:
        print("Mendeteksi pola candlestick...")
        # Menggunakan fungsi cdl_pattern dari pandas_ta untuk mendeteksi pola Engulfing
        # Akan menghasilkan kolom 'CDL_ENGULFING' dengan nilai:
        # 100 untuk Bullish Engulfing
        # -100 untuk Bearish Engulfing
        # 0 jika tidak ada pola
        df.ta.cdl_pattern(name="engulfing", append=True)

    df.dropna(inplace=True)
    print("Indikator berhasil dihitung.")
    return df

def check_major_trend(df):
    """Menganalisis tren utama pada timeframe tinggi (1D)."""
    print(f"Menganalisis tren utama pada timeframe {TREND_TIMEFRAME}...")
    last_close = df['close'].iloc[-1]
    trend_sma_value = df[f'SMA_{TREND_SMA_PERIOD}'].iloc[-1]
    
    if last_close > trend_sma_value:
        print(f"Tren Utama: BULLISH (Harga {last_close:.2f} > SMA {TREND_SMA_PERIOD} {trend_sma_value:.2f})")
        return "bullish"
    elif last_close < trend_sma_value:
        print(f"Tren Utama: BEARISH (Harga {last_close:.2f} < SMA {TREND_SMA_PERIOD} {trend_sma_value:.2f})")
        return "bearish"
    else:
        print("Tren Utama: NEUTRAL")
        return "neutral"

def check_entry_signal(df, major_trend):
    """
    Menganalisis sinyal entry berdasarkan tren, crossover, RSI, dan pola candlestick.
    """
    print(f"Menganalisis sinyal entry pada timeframe {SIGNAL_TIMEFRAME}...")
    if len(df) < 2:
        print("Data tidak cukup untuk mendeteksi sinyal.")
        return None, None
        
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    # Ambil nilai indikator
    sma_short_prev = prev_candle[f'SMA_{SMA_SHORT_PERIOD}']
    sma_long_prev = prev_candle[f'SMA_{SMA_LONG_PERIOD}']
    sma_short_curr = last_candle[f'SMA_{SMA_SHORT_PERIOD}']
    sma_long_curr = last_candle[f'SMA_{SMA_LONG_PERIOD}']
    rsi_curr = last_candle[f'RSI_{RSI_PERIOD}']
    
    # --- BARU: Cek hasil deteksi pola candlestick pada candle terakhir ---
    candlestick_signal = last_candle['CDL_ENGULFING']
    detected_pattern = None

    is_bullish_pattern = candlestick_signal == 100
    if is_bullish_pattern:
        detected_pattern = "Bullish Engulfing"

    is_bearish_pattern = candlestick_signal == -100
    if is_bearish_pattern:
        detected_pattern = "Bearish Engulfing"
        
    # Hanya cari sinyal BELI jika tren utama Bullish
    if major_trend == "bullish":
        is_golden_cross = sma_short_prev < sma_long_prev and sma_short_curr > sma_long_curr
        if is_golden_cross and rsi_curr > RSI_CONFIRMATION_LEVEL and is_bullish_pattern:
            print(f"Sinyal BELI terdeteksi (Golden Cross) dan terkonfirmasi oleh {detected_pattern}.")
            return "buy", detected_pattern

    # Hanya cari sinyal JUAL jika tren utama Bearish
    if major_trend == "bearish":
        is_death_cross = sma_short_prev > sma_long_prev and sma_short_curr < sma_long_curr
        if is_death_cross and rsi_curr < RSI_CONFIRMATION_LEVEL and is_bearish_pattern:
            print(f"Sinyal JUAL terdeteksi (Death Cross) dan terkonfirmasi oleh {detected_pattern}.")
            return "sell", detected_pattern
    
    print(f"Tidak ada sinyal entry yang valid sesuai dengan semua kriteria.")
    return None, None

def format_message(signal_type, df_signal, major_trend, pattern):
    """Memformat pesan notifikasi berdasarkan jenis sinyal."""
    current_price = df_signal['close'].iloc[-1]
    current_rsi = df_signal[f'RSI_{RSI_PERIOD}'].iloc[-1]
    
    if signal_type == "buy":
        title = "🚨 **SINYAL BELI: BTC/USDT** 🚨"
        strategy = "Golden Cross (4H) + Konfirmasi RSI (4H)"
    else:
        title = "📉 **SINYAL JUAL: BTC/USDT** 📉"
        strategy = "Death Cross (4H) + Konfirmasi RSI (4H)"

    message = (
        f"{title}\n\n"
        f"**Analisis Top-Down:**\n"
        f"  - **Tren Utama ({TREND_TIMEFRAME}):** {major_trend.upper()}\n"
        f"  - **Sinyal Entri ({SIGNAL_TIMEFRAME}):** Aktif\n\n"
        f"**Detail Sinyal:**\n"
        f"  - **Strategi:** {strategy}\n"
        f"  - **Konfirmasi Pola:** **{pattern}**\n" # <-- BARU
        f"  - **Harga Saat Ini:** ${current_price:,.2f}\n"
        f"  - **RSI(14):** {current_rsi:.2f}\n\n"
        f"*Disclaimer: Ini bukan nasihat keuangan. Lakukan riset Anda sendiri.*"
    )
    return message

async def send_telegram_message(message):
    """Mengirim pesan ke channel Telegram."""
    try:
        print("Mengirim notifikasi ke Telegram...")
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        print("Notifikasi berhasil dikirim.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")

# --- Manajemen Status Sinyal ---

def read_last_signal():
    try:
        with open(LAST_SIGNAL_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def write_last_signal(signal):
    with open(LAST_SIGNAL_FILE, 'w') as f:
        f.write(signal)

# --- FUNGSI UTAMA ---

async def main():
    check_credentials()
    
    # Langkah 1: Tentukan tren utama
    trend_df = fetch_data(SYMBOL, TREND_TIMEFRAME, LIMIT)
    if trend_df is None: return
    trend_df = calculate_indicators(trend_df, trend_sma=TREND_SMA_PERIOD)
    major_trend = check_major_trend(trend_df)
    if major_trend == "neutral":
        print("Tren pasar tidak jelas. Tidak mencari sinyal entry.")
        return

    # Langkah 2: Cari sinyal entry yang terkonfirmasi
    signal_df = fetch_data(SYMBOL, SIGNAL_TIMEFRAME, LIMIT)
    if signal_df is None: return
    signal_df = calculate_indicators(signal_df, sma_short=SMA_SHORT_PERIOD, sma_long=SMA_LONG_PERIOD, rsi=RSI_PERIOD, patterns=True)
    current_signal, detected_pattern = check_entry_signal(signal_df, major_trend)
    
    # Langkah 3: Kirim notifikasi jika ada sinyal baru
    if current_signal:
        last_signal = read_last_signal()
        if current_signal != last_signal:
            print(f"Sinyal baru ({current_signal}) ditemukan. Mengirim notifikasi...")
            message = format_message(current_signal, signal_df, major_trend, detected_pattern)
            await send_telegram_message(message)
            write_last_signal(current_signal)
        else:
            print(f"Sinyal saat ini ({current_signal}) sama dengan sinyal terakhir.")

if __name__ == "__main__":
    asyncio.run(main())

