# -*- coding: utf-8 -*-

"""
Skrip utama untuk menganalisis data harga BTC/USDT menggunakan Google Gemini
dengan pendekatan multi-timeframe dan data indikator teknis (TA-Lib).
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
    if df is None or df.empty:
        return None
    try:
        # Menghitung RSI, MACD, dan Bollinger Bands
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        
        # Mengambil baris terakhir dari data yang sudah dihitung
        latest = df.iloc[-1]
        
        # Mengemas hasil ke dalam dictionary, menangani kemungkinan nilai NaN
        indicators = {
            'RSI_14': f"{latest.get('RSI_14', 0):.2f}",
            'MACD': f"{latest.get('MACDh_12_26_9', 0):.2f}",
            'BB_Upper': f"{latest.get('BBU_20_2.0', 0):.2f}",
            'BB_Lower': f"{latest.get('BBL_20_2.0', 0):.2f}"
        }
        return indicators
    except Exception as e:
        print(f"Peringatan: Gagal menghitung indikator TA. Error: {e}")
        return None

def format_data_for_gemini(all_data, sr_levels=None, all_ta_indicators=None):
    """Mengubah semua data menjadi satu laporan teks komprehensif."""
    report = "Berikut adalah data harga dan indikator teknis untuk dianalisis:\n\n"
    
    # Menambahkan data mentah
    for tf, df in all_data.items():
        if df is not None and not df.empty:
            df_subset = df.copy().tail(60) # Mengirim 60 candle terakhir agar tidak terlalu panjang
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"--- Data Harga Timeframe: {tf} ---\n"
            report += df_subset.to_string(index=False)
            report += "\n\n"
            
    # Menambahkan data indikator teknis
    if all_ta_indicators:
        report += "--- Data Indikator Teknis (Nilai Terakhir) ---\n"
        for tf, indicators in all_ta_indicators.items():
            if indicators:
                report += f"Timeframe {tf}:\n"
                report += f"  - RSI(14): {indicators['RSI_14']}\n"
                report += f"  - MACD Histogram: {indicators['MACD']}\n"
                report += f"  - Bollinger Bands: Upper={indicators['BB_Upper']}, Lower={indicators['BB_Lower']}\n"
        report += "\n"

    # Menambahkan level S/R
    if sr_levels:
        report += "--- Level Support/Resistance Kunci (Pivot Points Harian) ---\n"
        for level, value in sr_levels.items():
            report += f"{level}: {value:,.2f}\n"
        report += "\n"
        
    return report

def get_gemini_analysis(price_data_report):
    """Mengirim laporan ke Gemini dan meminta rencana trading dalam format JSON."""
    try:
        print("Menghubungi Google Gemini untuk analisis komprehensif...")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            'gemini-2.5-turbo',
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        prompt = (
            "Anda adalah seorang trader dan analis teknikal profesional. "
            f"Tugas Anda adalah menganalisis data harga OHLCV dan data indikator teknis (RSI, MACD, Bollinger Bands) untuk {SYMBOL}. "
            "Lakukan analisis berikut:\n"
            "1. Identifikasi tren utama pada timeframe tinggi (1D, 4H) menggunakan data harga dan indikator.\n"
            "2. Gunakan level Support/Resistance (Pivot Points) yang disediakan sebagai acuan utama untuk menentukan potensi target.\n"
            "3. Cross-reference pembacaan RSI dan MACD untuk mengukur momentum dan potensi divergensi.\n"
            "4. Gunakan timeframe rendah (1H, 15M) untuk mencari konfirmasi dan sinyal entry yang presisi.\n"
            "5. Rangkum semua temuan Anda ke dalam satu rencana trading yang jelas.\n"
            "Berikan output HANYA dalam format JSON yang valid dengan kunci: 'action' ('Long', 'Short', 'Neutral'), 'entry' (float atau 'Market'), 'tp' (float), 'sl' (float), dan 'reasoning' (string singkat).\n\n"
            f"Berikut adalah data pasarnya:\n{price_data_report}"
        )
        
        response = model.generate_content(prompt)
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
        analysis = json.loads(cleaned_text)
        print(f"Gemini Analysis Result: {analysis}")
        return analysis
            
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons Gemini: {e}")
        return None

def format_signal_message(analysis, current_price):
    """Memformat pesan notifikasi rencana trading dari AI."""
    action = analysis.get('action', 'N/A').upper()
    entry = analysis.get('entry')
    tp, sl = analysis.get('tp', 0), analysis.get('sl', 0)
    reasoning = analysis.get('reasoning', 'N/A')
    entry_price_str = f"${entry:,.2f}" if isinstance(entry, (int, float)) else "Market"
    
    title = f"📈 **SINYAL AI: LONG {SYMBOL}** 📈" if action == 'LONG' else f"📉 **SINYAL AI: SHORT {SYMBOL}** 📉"
    if action not in ['LONG', 'SHORT']: return None

    return (
        f"{title}\n\n"
        f"Gemini AI telah merumuskan rencana trading berdasarkan analisis multi-timeframe.\n\n"
        f"**Harga Saat Ini:** ${current_price:,.2f}\n\n"
        f"**Rencana Trading:**\n"
        f"  - **Entri:** {entry_price_str}\n"
        f"  - **Take Profit (TP):** ${tp:,.2f}\n"
        f"  - **Stop Loss (SL):** ${sl:,.2f}\n\n"
        f"**Alasan Analisis:**\n"
        f"_{reasoning}_\n\n"
        f"*Disclaimer: Ini bukan nasihat keuangan. Lakukan riset Anda sendiri.*"
    )

def format_status_message(last_price, last_gemini_analysis):
    """Memformat pesan status harian."""
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    reason = last_gemini_analysis.get('reasoning', 'Menunggu peluang.')
    return (
        f"✅ **Bot Status: OK** ✅\n\n"
        f"**Waktu:** {now} WIB\n\n"
        f"**Status Pasar Terakhir:**\n"
        f"  - **Harga {SYMBOL}:** ${last_price:,.2f}\n"
        f"  - **Kesimpulan AI:** {last_gemini_analysis.get('action', 'N/A').upper()} - _{reason}_\n\n"
        f"*Tidak ada sinyal trading baru yang terdeteksi.*"
    )

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        if len(message) > 4096: message = message[:4090] + "\n..."
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
    
    all_market_data = await fetch_all_data(SYMBOL, TIMEFRAMES, CANDLE_COUNT_FOR_GEMINI)
    
    # Mode Debug untuk memverifikasi pengambilan data
    if DEBUG_FETCH_ONLY:
        tz = pytz.timezone('Asia/Jakarta')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        debug_message = f"⚙️ **Bot Debug Mode: Laporan Fetch** ⚙️\n\n"
        debug_message += f"**Waktu:** {now} WIB\n\n"
        debug_message += "**Status Pengambilan Data:**\n"
        success_count = 0
        for tf, df in all_market_data.items():
            status = "✅ Berhasil" if df is not None and not df.empty else "❌ Gagal"
            debug_message += f"  - **Timeframe {tf}:** {status}\n"
            if status == "✅ Berhasil": success_count += 1
        debug_message += "\nSemua data berhasil diambil." if success_count == len(TIMEFRAMES) else "\nAda masalah saat mengambil data."
        await send_telegram_message(debug_message)
        return

    if all_market_data.get('4h') is None or all_market_data['4h'].empty:
        await send_telegram_message("❌ **Bot Error:** Gagal mengambil data pasar utama (4h).")
        return
    last_price = all_market_data['4h']['close'].iloc[-1]

    # Menghitung indikator untuk setiap timeframe
    all_ta_indicators = {}
    for tf, df in all_market_data.items():
        print(f"Menghitung indikator TA untuk timeframe {tf}...")
        all_ta_indicators[tf] = calculate_ta_indicators(df)

    sr_levels = calculate_pivot_points(all_market_data.get('1d'))
    price_report = format_data_for_gemini(all_market_data, sr_levels, all_ta_indicators)
    analysis_result = get_gemini_analysis(price_report)
    
    if analysis_result is None:
        await send_telegram_message("❌ **Bot Error:** Gagal mendapatkan analisis dari Gemini AI.")
        return

    current_action = analysis_result.get('action', 'Neutral').upper()

    if current_action in ["LONG", "SHORT"]:
        last_signal = read_last_signal()
        if current_action != last_signal:
            message = format_signal_message(analysis_result, last_price)
            await send_telegram_message(message)
            write_last_signal(current_action)
            signal_sent = True
        else:
            print(f"Sinyal saat ini ({current_action}) sama dengan yang terakhir dikirim.")

    if not signal_sent:
        status_message = format_status_message(last_price, analysis_result)
        await send_telegram_message(status_message)

if __name__ == "__main__":
    asyncio.run(main())

