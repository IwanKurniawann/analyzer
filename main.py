# -*- coding: utf-8 -*-

"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif
menggunakan Google Gemini dengan pendekatan multi-timeframe, data indikator teknis,
dan Google Search Grounding untuk data sentimen dan pasar.
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
    """Menghitung indikator teknis kunci dan mengembalikan nilai terakhir."""
    if df is None or df.empty: return None
    try:
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        latest = df.iloc[-1]
        return {
            'RSI_14': f"{latest.get('RSI_14', 0):.2f}",
            'MACD': f"{latest.get('MACDh_12_26_9', 0):.2f}",
            'BB_Upper': f"{latest.get('BBU_20_2.0', 0):.2f}",
            'BB_Lower': f"{latest.get('BBL_20_2.0', 0):.2f}"
        }
    except Exception as e:
        print(f"Peringatan: Gagal menghitung indikator TA. Error: {e}")
        return None

def format_data_for_gemini(all_data, sr_levels=None, all_ta_indicators=None):
    """Mengubah semua data menjadi satu laporan teks komprehensif."""
    report = "Data teknis pasar untuk dianalisis:\n\n"
    if all_ta_indicators:
        report += "--- Data Indikator Teknis (Nilai Terakhir) ---\n"
        for tf, indicators in all_ta_indicators.items():
            if indicators:
                report += f"TF {tf}: RSI={indicators['RSI_14']}, MACD_H={indicators['MACD']}\n"
        report += "\n"

    if sr_levels:
        report += "--- Level Support/Resistance Kunci (Pivot Points Harian) ---\n"
        for level, value in sr_levels.items():
            report += f"{level}: {value:,.2f}\n"
        report += "\n"
    return report

def get_gemini_analysis(technical_data_report):
    """Mengirim laporan ke Gemini dan meminta analisis komprehensif dalam format JSON."""
    try:
        print("Menghubungi Google Gemini untuk analisis komprehensif...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        # --- PERBAIKAN: Menghapus parameter 'disable_attribution' ---
        tools = [genai.protos.Tool(
            google_search_retrieval=genai.protos.GoogleSearchRetrieval()
        )]
        
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            tools=tools
        )
        
        prompt = (
            f"Anda adalah tim analis keuangan kuantitatif elit. Tugas Anda adalah membuat laporan analisis pasar yang komprehensif untuk {SYMBOL}. "
            "Gunakan data teknis yang saya berikan DAN gunakan kemampuan pencarian internal Anda untuk menemukan data on-chain dan berita.\n\n"
            "DATA TEKNIS INTERNAL:\n"
            f"{technical_data_report}\n\n"
            "TUGAS ANALISIS (Isi setiap poin berdasarkan data teknis dan pencarian Anda):\n"
            "1.  **Candle**: Analisis 1-3 candle terakhir di timeframe 4H. Apakah ada pola signifikan (Doji, Engulfing, Hammer)?\n"
            "2.  **Chart**: Identifikasi pola chart mayor yang sedang terbentuk di timeframe 4H atau 1D (misal: 'Bull Flag', 'Rising Wedge', 'Sideways Range').\n"
            "3.  **Indikator**: Berikan kesimpulan dari data indikator yang ada. Apakah RSI overbought/oversold? Apakah MACD menunjukkan penguatan/pelemahan momentum?\n"
            "4.  **Berita Sentimen**: Lakukan pencarian. Apa sentimen pasar crypto secara umum saat ini (Fear, Greed, Neutral)? Adakah berita besar yang mempengaruhi {SYMBOL}?\n"
            "5.  **Bias Harga**: Berdasarkan semua data, apa bias arah harga untuk 12 jam ke depan (Bullish, Bearish, Sideways)?\n"
            "6.  **Volatilitas**: Bagaimana tingkat volatilitas saat ini (Tinggi, Sedang, Rendah)?\n"
            "7.  **Market Depth**: Lakukan pencarian untuk data futures {SYMBOL}. Cari nilai perkiraan untuk Funding Rate (Positif/Negatif), Open Interest (Naik/Turun), dan area likuidasi besar terdekat.\n"
            "8.  **Level SR**: Sebutkan level Resistance dan Support terkuat berdasarkan data Pivot dan analisis Anda.\n"
            "9.  **Faktor Lain**: Lakukan pencarian. Adakah event besar (rilis data ekonomi, unlock token) dalam 12 jam ke depan?\n"
            "10. **Entry Ideal**: Berikan satu level harga entri ideal untuk posisi Long dan satu untuk Short.\n"
            "11. **Confident Score**: Berikan skor kepercayaan (0-100) untuk bias harga yang Anda tentukan.\n"
            "12. **Kesimpulan**: Berikan kesimpulan trading dalam 1-2 kalimat (misal: 'Pasar bullish, tunggu konfirmasi di support untuk entry Long.')\n\n"
            "FORMAT OUTPUT:\n"
            "Berikan output HANYA dalam format JSON yang valid, tanpa markdown. Gunakan kunci berikut: 'candle', 'chart', 'indicator', 'sentiment', 'bias', 'volatility', 'market_depth', 'sr_levels', 'other_factors', 'ideal_entry', 'confidence_score', 'conclusion'. Untuk 'market_depth' dan 'sr_levels' gunakan sub-objek."
        )
        
        response = model.generate_content(prompt)
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
        analysis = json.loads(cleaned_text)
        print("Gemini Analysis Result Received.")
        return analysis
            
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons Gemini: {e}")
        return None

def format_full_analysis_message(analysis, current_price):
    """Memformat pesan notifikasi analisis komprehensif dari AI."""
    # Ekstrak semua data dari JSON dengan aman
    candle = analysis.get('candle', 'N/A')
    chart = analysis.get('chart', 'N/A')
    indicator = analysis.get('indicator', 'N/A')
    sentiment = analysis.get('sentiment', 'N/A')
    bias = analysis.get('bias', 'N/A').upper()
    volatility = analysis.get('volatility', 'N/A')
    
    market_depth = analysis.get('market_depth', {})
    funding_rate = market_depth.get('Funding Rate', 'N/A')
    liquidation = market_depth.get('Liquidation', 'N/A')
    open_interest = market_depth.get('Open Interest', 'N/A')
    
    sr_levels = analysis.get('sr_levels', {})
    resistance = sr_levels.get('Resistance kuat', 'N/A')
    support = sr_levels.get('Support kuat', 'N/A')
    
    other_factors = analysis.get('other_factors', 'Tidak ada')
    
    ideal_entry = analysis.get('ideal_entry', {})
    long_entry = ideal_entry.get('Long', 'N/A')
    short_entry = ideal_entry.get('Short', 'N/A')
    
    confidence = analysis.get('confidence_score', 0)
    conclusion = analysis.get('conclusion', 'N/A')

    # Tentukan emoji utama berdasarkan bias
    if bias == 'BULLISH':
        main_emoji = '🟢'
    elif bias == 'BEARISH':
        main_emoji = '🔴'
    else:
        main_emoji = '⚪️'
        
    message = (
        f"*{main_emoji} LAPORAN ANALISIS AI UNTUK {SYMBOL}*\n\n"
        f"Berikut adalah analisis pasar komprehensif yang dihasilkan oleh Gemini AI.\n"
        f"*Harga Saat Ini: ${current_price:,.2f}*\n\n"
        f"----------------------------------------\n\n"
        f"*1. Analisis Candle (4H):*\n_{candle}_\n\n"
        f"*2. Pola Chart (1D/4H):*\n_{chart}_\n\n"
        f"*3. Kesimpulan Indikator:*\n_{indicator}_\n\n"
        f"*4. Sentimen Pasar:*\n_{sentiment}_\n\n"
        f"*5. Bias Harga (12 Jam):*\n*{bias}*\n\n"
        f"*6. Volatilitas Saat Ini:*\n_{volatility}_\n\n"
        f"*7. Market Depth (Futures):*\n"
        f"  - Funding Rate: _{funding_rate}_\n"
        f"  - Open Interest: _{open_interest}_\n"
        f"  - Zona Likuidasi Terdekat: _{liquidation}_\n\n"
        f"*8. Level Support & Resistance:*\n"
        f"  - Resistance Kuat: *{resistance}*\n"
        f"  - Support Kuat: *{support}*\n\n"
        f"*9. Faktor Eksternal (12 Jam):*\n_{other_factors}_\n\n"
        f"*10. Zona Entry Ideal:*\n"
        f"  - Long: *{long_entry}*\n"
        f"  - Short: *{short_entry}*\n\n"
        f"----------------------------------------\n\n"
        f"📌 *Kesimpulan & Skor Kepercayaan:*\n"
        f"_{conclusion}_ (*Skor: {confidence}%*)\n\n"
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
        print(f"Menghitung indikator TA untuk timeframe {tf}...")
        all_ta_indicators[tf] = calculate_ta_indicators(df)

    sr_levels = calculate_pivot_points(all_market_data.get('1d'))
    technical_report = format_data_for_gemini(all_market_data, sr_levels, all_ta_indicators)
    
    full_analysis_result = get_gemini_analysis(technical_report)
    
    if full_analysis_result is None:
        await send_telegram_message("❌ **Bot Error:** Gagal mendapatkan analisis komprehensif dari Gemini AI.")
        return

    # Kirim laporan lengkap ke Telegram
    report_message = format_full_analysis_message(full_analysis_result, last_price)
    await send_telegram_message(report_message)

if __name__ == "__main__":
    asyncio.run(main())

