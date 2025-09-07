# -*- coding: utf-8 -*-

"""
Skrip utama untuk menganalisis data harga BTC/USDT,
menghasilkan sinyal perdagangan, dan mengirim notifikasi ke Telegram.
Versi ini menggunakan API Bybit dan konfirmasi analisis dari Google Gemini.
"""

import os
import sys
import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import telegram
import google.generativeai as genai
from datetime import datetime
import pytz

# --- KONFIGRASI ---
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
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') # <-- BARU

def check_credentials():
    """Memeriksa apakah semua kredensial sudah diatur."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("Error: Pastikan GEMINI_API_KEY sudah diatur di GitHub Secrets.")
        sys.exit(1)

# --- FUNGSI BARU: Analisis dengan Gemini API ---
def get_gemini_analysis(summary):
    """
    Mengirim ringkasan pasar ke Gemini dan meminta analisis.
    """
    try:
        print("Menghubungi Google Gemini untuk analisis lanjutan...")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = (
            f"Berpikir bertahap dan mendalam, Anda adalah seorang analis pasar keuangan ahli. "
            f"Berdasarkan ringkasan berikut, berikan kesimpulan analisis Anda hanya dalam satu kata: 'BULLISH', 'BEARISH', atau 'NEUTRAL'. "
            f"Jangan memberikan penjelasan apa pun. Ringkasan pasar: \n\n"
            f"{summary}"
        )
        
        response = model.generate_content(prompt)
        result = response.text.strip().upper()
        print(f"Gemini Analysis Result: {result}")

        if result in ["BULLISH", "BEARISH", "NEUTRAL"]:
            return result
        else:
            print(f"Peringatan: Gemini memberikan respons yang tidak valid: {result}")
            return None # Respons tidak sesuai format
            
    except Exception as e:
        print(f"Error saat menghubungi Gemini API: {e}")
        return None

def fetch_data(symbol, timeframe, limit):
    """
    Mengambil data OHLCV dari Bybit menggunakan ccxt.
    """
    try:
        print(f"Mengambil {limit} data candle terakhir untuk {symbol} pada timeframe {timeframe} dari Bybit...")
        exchange = ccxt.kucoin() 
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print("Data berhasil diambil.")
        return df
    except Exception as e:
        print(f"Error saat mengambil data dari bursa: {e}")
        return None

def calculate_indicators(df, sma_short=None, sma_long=None, rsi=None, trend_sma=None, patterns=False):
    """Menghitung indikator teknis."""
    print(f"Menghitung indikator teknis...")
    if sma_short and sma_long:
        df[f'SMA_{sma_short}'] = ta.sma(df['close'], length=sma_short)
        df[f'SMA_{sma_long}'] = ta.sma(df['close'], length=sma_long)
    if rsi:
        df[f'RSI_{rsi}'] = ta.rsi(df['close'], length=rsi)
    if trend_sma:
        df[f'SMA_{trend_sma}'] = ta.sma(df['close'], length=trend_sma)
    if patterns:
        df.ta.cdl_pattern(name="engulfing", append=True)
    df.dropna(inplace=True)
    return df

def check_major_trend(df):
    """Menganalisis tren utama pada timeframe tinggi (1D)."""
    last_close = df['close'].iloc[-1]
    trend_sma_value = df[f'SMA_{TREND_SMA_PERIOD}'].iloc[-1]
    if last_close > trend_sma_value: return "bullish"
    if last_close < trend_sma_value: return "bearish"
    return "neutral"

def check_entry_signal(df, major_trend):
    """Menganalisis sinyal entry berdasarkan aturan teknis."""
    if len(df) < 2: return None, None
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    sma_short_prev = prev_candle[f'SMA_{SMA_SHORT_PERIOD}']
    sma_long_prev = prev_candle[f'SMA_{SMA_LONG_PERIOD}']
    sma_short_curr = last_candle[f'SMA_{SMA_SHORT_PERIOD}']
    sma_long_curr = last_candle[f'SMA_{SMA_LONG_PERIOD}']
    rsi_curr = last_candle[f'RSI_{RSI_PERIOD}']
    candlestick_signal = last_candle['CDL_ENGULFING']
    
    detected_pattern = None
    is_bullish_pattern = candlestick_signal == 100
    if is_bullish_pattern: detected_pattern = "Bullish Engulfing"
    is_bearish_pattern = candlestick_signal == -100
    if is_bearish_pattern: detected_pattern = "Bearish Engulfing"
        
    if major_trend == "bullish":
        is_golden_cross = sma_short_prev < sma_long_prev and sma_short_curr > sma_long_curr
        if is_golden_cross and rsi_curr > RSI_CONFIRMATION_LEVEL and is_bullish_pattern:
            return "buy", detected_pattern

    if major_trend == "bearish":
        is_death_cross = sma_short_prev > sma_long_prev and sma_short_curr < sma_long_curr
        if is_death_cross and rsi_curr < RSI_CONFIRMATION_LEVEL and is_bearish_pattern:
            return "sell", detected_pattern
    
    return None, None

def format_message(signal_type, df_signal, major_trend, pattern, gemini_confirm=False):
    """Memformat pesan notifikasi."""
    current_price = df_signal['close'].iloc[-1]
    current_rsi = df_signal[f'RSI_{RSI_PERIOD}'].iloc[-1]
    tf = SIGNAL_TIMEFRAME.upper()
    
    if signal_type == "buy":
        title = f"🚨 **SINYAL BELI: {SYMBOL}** 🚨"
        strategy = f"Golden Cross ({tf}) + Konfirmasi RSI ({tf})"
    else:
        title = f"📉 **SINYAL JUAL: {SYMBOL}** 📉"
        strategy = f"Death Cross ({tf}) + Konfirmasi RSI ({tf})"

    # --- BARU: Menambahkan status konfirmasi Gemini ---
    gemini_status = "Terkonfirmasi oleh AI" if gemini_confirm else ""

    message = (
        f"{title}\n\n"
        f"**Analisis Top-Down:**\n"
        f"  - **Tren Utama ({TREND_TIMEFRAME.upper()}):** {major_trend.upper()}\n"
        f"  - **Sinyal Entri ({tf}):** Aktif\n\n"
        f"**Detail Sinyal:**\n"
        f"  - **Strategi:** {strategy}\n"
        f"  - **Konfirmasi Pola:** **{pattern}**\n"
        f"  - **Harga Saat Ini:** ${current_price:,.2f}\n"
        f"  - **RSI({RSI_PERIOD}):** {current_rsi:.2f}\n"
        f"  - **Analisis AI:** **{gemini_status}**\n\n" # <-- BARU
        f"*Disclaimer: Ini bukan nasihat keuangan. Lakukan riset Anda sendiri.*"
    )
    return message

def format_status_message(major_trend, last_price):
    """Memformat pesan status."""
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    return (
        f"✅ **Bot Status: OK** ✅\n\n"
        f"Skrip analisis berhasil dijalankan pada:\n"
        f"**Waktu:** {now} WIB\n\n"
        f"**Status Pasar Saat Ini:**\n"
        f"  - **Harga {SYMBOL}:** ${last_price:,.2f}\n"
        f"  - **Tren Utama ({TREND_TIMEFRAME.upper()}):** {major_trend.upper()}\n\n"
        f"*Tidak ada sinyal trading baru yang sesuai dengan strategi saat ini.*"
    )

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Notifikasi berhasil dikirim.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")

def read_last_signal():
    try:
        with open(LAST_SIGNAL_FILE, 'r') as f: return f.read().strip()
    except FileNotFoundError: return None

def write_last_signal(signal):
    with open(LAST_SIGNAL_FILE, 'w') as f: f.write(signal)

async def main():
    check_credentials()
    signal_sent = False
    
    trend_df = fetch_data(SYMBOL, TREND_TIMEFRAME, LIMIT)
    if trend_df is None: return
    trend_df = calculate_indicators(trend_df, trend_sma=TREND_SMA_PERIOD)
    major_trend = check_major_trend(trend_df)
    last_price = trend_df['close'].iloc[-1]

    if major_trend in ["bullish", "bearish"]:
        signal_df = fetch_data(SYMBOL, SIGNAL_TIMEFRAME, LIMIT)
        if signal_df is None: return
        signal_df = calculate_indicators(signal_df, sma_short=SMA_SHORT_PERIOD, sma_long=SMA_LONG_PERIOD, rsi=RSI_PERIOD, patterns=True)
        current_signal, detected_pattern = check_entry_signal(signal_df, major_trend)
        
        if current_signal:
            last_signal = read_last_signal()
            if current_signal != last_signal:
                # --- LOGIKA BARU: Konfirmasi dengan Gemini ---
                market_summary = (
                    f"Tren utama pada timeframe {TREND_TIMEFRAME} adalah {major_trend}. "
                    f"Pada timeframe {SIGNAL_TIMEFRAME}, sinyal teknis menunjukkan '{current_signal.upper()}' "
                    f"yang dipicu oleh {('Golden Cross' if current_signal == 'buy' else 'Death Cross')} "
                    f"dan dikonfirmasi oleh pola candlestick '{detected_pattern}'. "
                    f"RSI({RSI_PERIOD}) saat ini adalah {signal_df[f'RSI_{RSI_PERIOD}'].iloc[-1]:.2f}."
                )
                gemini_verdict = get_gemini_analysis(market_summary)

                # Sinyal dikirim jika analisis Gemini sesuai dengan sinyal teknis
                if (current_signal == "buy" and gemini_verdict == "BULLISH") or \
                   (current_signal == "sell" and gemini_verdict == "BEARISH"):
                    
                    print("Konfirmasi dari Gemini sesuai. Mengirim notifikasi sinyal...")
                    message = format_message(current_signal, signal_df, major_trend, detected_pattern, gemini_confirm=True)
                    await send_telegram_message(message)
                    write_last_signal(current_signal)
                    signal_sent = True
                else:
                    print(f"Sinyal teknis ({current_signal}) tidak dikonfirmasi oleh Gemini ({gemini_verdict}). Sinyal diabaikan.")
            else:
                print(f"Sinyal saat ini ({current_signal}) sama dengan sinyal terakhir.")
    
    if not signal_sent:
        print("Tidak ada sinyal trading baru atau sinyal tidak terkonfirmasi. Mengirim pesan status...")
        status_message = format_status_message(major_trend, last_price)
        await send_telegram_message(status_message)

if __name__ == "__main__":
    asyncio.run(main())

