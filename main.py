# -*- coding: utf-8 -*-

"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif
menggunakan Google Gemini. Versi ini fokus pada analisis teknikal murni
dari data multi-timeframe dan indikator untuk mengurangi penggunaan API.
"""

import os
import sys
import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import telegram
import google.generativeai as genai
import json
from datetime import datetime
import pytz

# --- KONFIGURASI ---
SYMBOL = 'SOL/USDT'
TIMEFRAMES = ['1d', '4h', '1h', '15m']
CANDLE_COUNT_FOR_GEMINI = 100

DEBUG_FETCH_ONLY = False
LAST_SIGNAL_FILE = "last_signal.txt"

# --- KREDENSIAL ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def check_credentials():
    """Memeriksa kredensial."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        sys.exit("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
    if not GEMINI_API_KEY and not DEBUG_FETCH_ONLY:
        sys.exit("Error: Pastikan GEMINI_API_KEY sudah diatur di GitHub Secrets.")

async def fetch_all_data(symbol, timeframes, limit):
    """Mengambil data OHLCV untuk semua timeframe."""
    all_data = {}
    exchange = ccxt.kucoin()
    for tf in timeframes:
        try:
            print(f"Mengambil {limit} data candle terakhir untuk {symbol} pada timeframe {tf}...")
            ohlcv = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            all_data[tf] = df
            print(f"Data untuk timeframe {tf} berhasil diambil.")
        except Exception as e:
            print(f"Error saat mengambil data untuk timeframe {tf}: {e}")
            all_data[tf] = None
    return all_data

def calculate_pivot_points(df):
    """Menghitung level Pivot Point Classic."""
    if len(df) < 2: return None
    last_candle = df.iloc[-2]
    high, low, close = last_candle['high'], last_candle['low'], last_candle['close']
    pivot = (high + low + close) / 3
    return {
        'R2': pivot + (high - low), 'R1': (2 * pivot) - low,
        'Pivot': pivot,
        'S1': (2 * pivot) - high, 'S2': pivot - (high - low)
    }

def calculate_ta_indicators(df):
    """Menghitung indikator teknis kunci."""
    if df is None or df.empty: return None
    try:
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        latest = df.iloc[-1]
        return {
            'RSI_14': f"{latest.get('RSI_14', 0):.2f}",
            'MACD_H': f"{latest.get('MACDh_12_26_9', 0):.2f}"
        }
    except Exception as e:
        print(f"Peringatan: Gagal menghitung indikator TA. Error: {e}")
        return None

def format_data_for_gemini(all_data, sr_levels=None, all_ta_indicators=None):
    """Mengubah data teknis menjadi laporan teks."""
    report = "Data teknis pasar untuk dianalisis:\n\n"
    if all_ta_indicators:
        report += "--- Data Indikator Teknis (Nilai Terakhir) ---\n"
        for tf, indicators in all_ta_indicators.items():
            if indicators:
                report += f"TF {tf}: RSI={indicators['RSI_14']}, MACD_H={indicators['MACD_H']}\n"
        report += "\n"

    if sr_levels:
        report += "--- Level Support/Resistance Kunci (Pivot Points Harian) ---\n"
        for level, value in sr_levels.items():
            report += f"{level}: {value:,.2f}\n"
        report += "\n"
        
    # Hanya melampirkan data harga mentah dari timeframe kunci
    key_timeframes = ['4h', '1h']
    for tf in key_timeframes:
        df = all_data.get(tf)
        if df is not None and not df.empty:
            df_subset = df.copy().tail(20) # Mengirim 20 candle terakhir
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"--- Data Harga Timeframe: {tf} ---\n"
            report += df_subset.to_string(index=False)
            report += "\n\n"
            
    return report

def get_gemini_analysis(technical_data_report):
    """Mengirim laporan teknis ke Gemini dan meminta rencana trading dalam format JSON."""
    try:
        print("Menghubungi Google Gemini untuk analisis teknikal...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        model = genai.GenerativeModel(
            'gemini-2.0-flash',
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        prompt = (
            f"Anda adalah seorang analis teknikal murni. Tugas Anda adalah membuat rencana trading untuk {SYMBOL} hanya berdasarkan data teknis yang saya berikan.\n\n"
            "DATA TEKNIS:\n"
            f"{technical_data_report}\n\n"
            "TUGAS ANALISIS (Isi setiap poin hanya dari data yang ada):\n"
            "1.  **Struktur Pasar**: Berdasarkan data harga, apa struktur pasar saat ini (Trending Up, Trending Down, Sideways/Range)?\n"
            "2.  **Kekuatan Indikator**: Bagaimana kekuatan momentum berdasarkan RSI dan MACD di timeframe kunci (4H, 1H)?\n"
            "3.  **Level Kunci**: Identifikasi level Support dan Resistance terdekat dan terkuat dari data Pivot Points yang diberikan.\n"
            "4.  **Bias Harga**: Apa bias arah harga untuk beberapa jam ke depan (Bullish, Bearish, Neutral)?\n"
            "5.  **Rencana Trading**: Buat satu rencana trading yang paling logis (Long atau Short) dengan Entry, TP, dan SL yang jelas. TP dan SL harus menargetkan atau berada di dekat level Pivot.\n"
            "6.  **Kesimpulan**: Berikan kesimpulan trading dalam satu kalimat.\n\n"
            "FORMAT OUTPUT:\n"
            "Berikan output HANYA dalam format JSON yang valid. Gunakan kunci berikut: 'structure', 'indicators', 'key_levels', 'bias', 'trade_plan', dan 'conclusion'. Untuk 'trade_plan' dan 'key_levels' gunakan sub-objek."
        )
        
        response = model.generate_content(prompt)
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
        analysis = json.loads(cleaned_text)
        print("Gemini Analysis Result Received.")
        return analysis
            
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons Gemini: {e}")
        return None

def format_analysis_message(analysis, current_price):
    """Memformat pesan notifikasi analisis teknikal dari AI."""
    structure = analysis.get('structure', 'N/A')
    indicators = analysis.get('indicators', 'N/A')
    bias = analysis.get('bias', 'N/A').upper()
    
    key_levels = analysis.get('key_levels', {})
    resistance = key_levels.get('Resistance', 'N/A')
    support = key_levels.get('Support', 'N/A')
    
    trade_plan = analysis.get('trade_plan', {})
    action = trade_plan.get('Action', 'N/A').upper()
    entry = trade_plan.get('Entry', 'N/A')
    tp = trade_plan.get('TP', 'N/A')
    sl = trade_plan.get('SL', 'N/A')
    
    conclusion = analysis.get('conclusion', 'N/A')

    if action == 'LONG':
        main_emoji = '🟢'
    elif action == 'SHORT':
        main_emoji = '🔴'
    else:
        main_emoji = '⚪️'
        
    message = (
        f"*{main_emoji} ANALISIS TEKNIKAL AI UNTUK {SYMBOL}*\n\n"
        f"*Harga Saat Ini: ${current_price:,.2f}*\n\n"
        f"----------------------------------------\n\n"
        f"*Struktur Pasar:*\n_{structure}_\n\n"
        f"*Kekuatan Indikator:*\n_{indicators}_\n\n"
        f"*Level Kunci:*\n"
        f"  - Resistance: *{resistance}*\n"
        f"  - Support: *{support}*\n\n"
        f"*Bias Harga Jangka Pendek:*\n*{bias}*\n\n"
        f"----------------------------------------\n\n"
        f"📌 *Rencana Trading & Kesimpulan:*\n"
        f"  - **Aksi:** *{action}*\n"
        f"  - **Entry:** *{entry}*\n"
        f"  - **Take Profit:** *{tp}*\n"
        f"  - **Stop Loss:** *{sl}*\n\n"
        f"_{conclusion}_\n\n"
        f"*Disclaimer: Ini bukan nasihat keuangan.*"
    )
    return message

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        if len(message) > 4096: message = message[:4090] + "\n..."
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Notifikasi berhasil dikirim.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")

async def main():
    check_credentials()
    
    all_market_data = await fetch_all_data(SYMBOL, TIMEFRAMES, CANDLE_COUNT_FOR_GEMINI)
    
    if all_market_data.get('4h') is None or all_market_data['4h'].empty:
        await send_telegram_message("❌ **Bot Error:** Gagal mengambil data pasar utama (4h).")
        return
    last_price = all_market_data['4h']['close'].iloc[-1]

    all_ta_indicators = {}
    for tf, df in all_market_data.items():
        all_ta_indicators[tf] = calculate_ta_indicators(df)

    sr_levels = calculate_pivot_points(all_market_data.get('1d'))
    technical_report = format_data_for_gemini(all_market_data, sr_levels, all_ta_indicators)
    
    analysis_result = get_gemini_analysis(technical_report)
    
    if analysis_result is None:
        await send_telegram_message("❌ **Bot Error:** Gagal mendapatkan analisis dari Gemini AI.")
        return

    report_message = format_analysis_message(analysis_result, last_price)
    await send_telegram_message(report_message)

if __name__ == "__main__":
    asyncio.run(main())

