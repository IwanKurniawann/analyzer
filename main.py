# -*- coding: utf-8 -*-
"""
main.py

Skrip ini adalah implementasi Python dari strategi trading Pine Script 
"Strong Engulfing/Reversal Strategy v8". Skrip ini mengambil data pasar
dari KuCoin, menganalisisnya berdasarkan aturan strategi, dan jika sinyal
terdeteksi, skrip akan meminta analisis dari Google Gemini sebelum 
mengirimkan notifikasi komprehensif ke Telegram.
"""

import os
import sys
import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import telegram
import google.generativeai as genai
from dotenv import load_dotenv

# --- 1. KONFIGURASI ---
load_dotenv()

CONFIG = {
    'symbol': 'SOL/USDT',
    'timeframe': '1h',
    'exchange': 'kucoin',
    'ohlcv_limit': 200,
    
    'strategy': {
        'buy_threshold': 3,
        'body_multiplier': 1.1,
        'trend_sma_length': 50,
        'rsi_length': 14,
        'atr_length': 14,
        'rsi_momentum_threshold': 55
    }
}

# --- 2. KREDENSIAL ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def check_credentials():
    """Memeriksa apakah semua kredensial yang dibutuhkan sudah tersedia."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("Error: Pastikan GEMINI_API_KEY sudah diatur.")
        sys.exit(1)

# --- 3. FUNGSI ANALISIS & PEMROSESAN DATA ---

async def fetch_data(symbol, timeframe, limit, exchange_id):
    """Mengambil data OHLCV dari bursa."""
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
        print(f"Mengambil data untuk {symbol}...")
        ohlcv = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Gagal mengambil data: {e}")
        return None

def calculate_indicators(df, config):
    """Menghitung indikator teknikal."""
    try:
        df.ta.sma(length=config['trend_sma_length'], append=True)
        df.ta.rsi(length=config['rsi_length'], append=True)
        df.ta.atr(length=config['atr_length'], append=True)
        return df
    except Exception as e:
        print(f"Gagal menghitung indikator: {e}")
        return None

def check_strategy_signal(df, config):
    """Mengevaluasi kondisi strategi dan mengembalikan data sinyal jika ditemukan."""
    if len(df) < 2: return None

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    bullish_score = 0
    score_details = []

    # 1. Skor Candlestick
    body_size = abs(latest['close'] - latest['open'])
    prev_body_size = abs(previous['close'] - previous['open'])
    is_bullish_engulfing = (
        previous['close'] < previous['open'] and latest['close'] > latest['open'] and
        latest['open'] < previous['close'] and latest['close'] > previous['open'] and
        body_size > prev_body_size * config['body_multiplier']
    )
    if is_bullish_engulfing:
        bullish_score += 2
        score_details.append("Pola Bullish Engulfing (+2)")

    # 2. Skor Tren
    sma_col = f"SMA_{config['trend_sma_length']}"
    if latest['close'] > latest[sma_col]:
        bullish_score += 1
        score_details.append(f"Harga di atas SMA{config['trend_sma_length']} (+1)")

    # 3. Skor Momentum
    rsi_col = f"RSI_{config['rsi_length']}"
    if latest[rsi_col] > config['rsi_momentum_threshold']:
        bullish_score += 1
        score_details.append(f"RSI > {config['rsi_momentum_threshold']} (+1)")

    # 4. Skor Volatilitas
    atr_col = f"ATRr_{config['atr_length']}"
    if latest[atr_col] > previous[atr_col]:
        bullish_score += 1
        score_details.append("Volatilitas Meningkat (ATR) (+1)")

    print(f"Evaluasi Sinyal: Skor Bullish = {bullish_score} (Ambang Batas: {config['buy_threshold']})")

    if bullish_score >= config['buy_threshold']:
        return {
            "score": bullish_score,
            "details": score_details,
            "price": latest['close'],
            "rsi": latest[rsi_col],
            "sma": latest[sma_col],
            "atr": latest[atr_col]
        }
    return None

def get_gemini_analysis(signal_data, symbol, timeframe):
    """Meminta analisis dari Google Gemini berdasarkan data sinyal."""
    try:
        print("Menghubungi Google Gemini untuk analisis...")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')

        prompt = (
            "Anda adalah seorang analis pasar crypto senior. Sebuah sinyal beli dari strategi 'Strong Engulfing' baru saja terdeteksi. "
            f"Aset: {symbol}, Timeframe: {timeframe}.\n\n"
            "Berikut adalah data pemicu sinyal:\n"
            f"- Harga Saat Ini: ${signal_data['price']:,.4f}\n"
            f"- Skor Sinyal: {signal_data['score']}\n"
            f"- Pemicu: {', '.join(signal_data['details'])}\n"
            f"- Indikator: RSI={signal_data['rsi']:.2f}, SMA={signal_data['sma']:.2f}\n\n"
            "Tugas Anda:\n"
            "1. Berikan analisis singkat (2-3 kalimat) mengenai kekuatan dan konteks sinyal ini. Apakah ini sinyal yang kuat? Apa yang perlu diwaspadai?\n"
            "2. Berikan satu rekomendasi langkah selanjutnya yang konkret dan hati-hati untuk seorang trader.\n\n"
            "Format jawaban Anda dengan ringkas dan jelas."
        )
        
        response = model.generate_content(prompt)
        print("Analisis dari Gemini berhasil diterima.")
        return response.text
    except Exception as e:
        print(f"Gagal mendapatkan analisis dari Gemini: {e}")
        return "Analisis AI tidak tersedia saat ini karena terjadi kesalahan teknis."

# --- 4. FUNGSI NOTIFIKASI ---

def format_telegram_message(signal_data, gemini_analysis, symbol, timeframe):
    """Memformat pesan akhir untuk dikirim ke Telegram."""
    message = (
        f"🟢 *Sinyal Beli Terdeteksi untuk {symbol}*\n\n"
        f"**Timeframe:** `{timeframe}`\n"
        f"**Harga Saat Ini:** `${signal_data['price']:,.4f}`\n"
        f"----------------------------------------\n"
        f"**Pemicu Sinyal (Skor: {signal_data['score']})**\n"
        f"- {', '.join(signal_data['details'])}\n\n"
        f"**Analisis dari Gemini AI:**\n"
        f"_{gemini_analysis}_\n\n"
        f"*Disclaimer: Ini adalah notifikasi otomatis. Selalu lakukan riset Anda sendiri (DYOR).*"
    )
    return message

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        print("Notifikasi berhasil dikirim ke Telegram.")
    except Exception as e:
        print(f"Gagal mengirim pesan ke Telegram: {e}")

# --- 5. FUNGSI UTAMA (MAIN) ---

async def main():
    """Fungsi orkestrasi utama."""
    check_credentials()
    
    market_data = await fetch_data(
        CONFIG['symbol'], CONFIG['timeframe'], CONFIG['ohlcv_limit'], CONFIG['exchange']
    )
    if market_data is None or market_data.empty: return

    market_data_with_ta = calculate_indicators(market_data, CONFIG['strategy'])
    if market_data_with_ta is None: return

    signal_data = check_strategy_signal(market_data_with_ta, CONFIG['strategy'])

    if signal_data:
        print("Sinyal ditemukan! Memproses analisis AI...")
        gemini_analysis = get_gemini_analysis(signal_data, CONFIG['symbol'], CONFIG['timeframe'])
        
        notification_message = format_telegram_message(
            signal_data, gemini_analysis, CONFIG['symbol'], CONFIG['timeframe']
        )
        await send_telegram_message(notification_message)
    else:
        print("Tidak ada sinyal beli yang ditemukan.")

if __name__ == "__main__":
    asyncio.run(main())

