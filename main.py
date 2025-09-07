# -*- coding: utf-8 -*-

"""
Skrip utama untuk menganalisis data harga BTC/USDT menggunakan Google Gemini
dengan pendekatan multi-timeframe (1D, 4H, 1H, 15M) untuk menghasilkan
rencana trading yang komprehensif (Entry, TP, SL).
Versi ini menambahkan perhitungan Support/Resistance otomatis.
"""

import os
import sys
import ccxt
import pandas as pd
import asyncio
import telegram
import google.generativeai as genai
import json
from datetime import datetime
import pytz

# --- KONFIGURASI ---
SYMBOL = 'SOL/USDT'
TIMEFRAMES = ['1d', '4h', '1h', '15m']
CANDLE_COUNT_FOR_GEMINI = 100 # Jumlah candle per timeframe untuk dianalisis

# Atur ke True untuk hanya mengambil data dan mengirim laporan status fetch ke Telegram.
# Mode debug sekarang akan mengirim 5 baris data mentah terakhir per timeframe.
DEBUG_FETCH_ONLY = False

LAST_SIGNAL_FILE = "last_signal.txt"

# --- KREDENSIAL (diambil dari GitHub Secrets) ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def check_credentials():
    """Memeriksa apakah semua kredensial sudah diatur."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
        sys.exit(1)
    if not GEMINI_API_KEY and not DEBUG_FETCH_ONLY: # Hanya cek Gemini key jika tidak dalam mode debug
        print("Error: Pastikan GEMINI_API_KEY sudah diatur di GitHub Secrets.")
        sys.exit(1)

async def fetch_all_data(symbol, timeframes, limit):
    """Mengambil data OHLCV untuk semua timeframe yang ditentukan."""
    all_data = {}
    exchange = ccxt.kucoin()
    for tf in timeframes:
        try:
            print(f"Mengambil {limit} data candle terakhir untuk {symbol} pada timeframe {tf}...")
            # Menggunakan asyncio.to_thread untuk menjalankan fungsi sinkron di dalam loop asinkron
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
    """Menghitung level Pivot Point Classic berdasarkan data candle sebelumnya (harian)."""
    if len(df) < 2:
        return None
        
    last_candle = df.iloc[-2] # Menggunakan data kemarin (candle sebelum terakhir)
    high = last_candle['high']
    low = last_candle['low']
    close = last_candle['close']
    
    pivot = (high + low + close) / 3
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    
    levels = {
        'R2': r2,
        'R1': r1,
        'Pivot': pivot,
        'S1': s1,
        'S2': s2
    }
    print(f"Calculated Pivot Levels (based on previous day): {levels}")
    return levels

def format_data_for_gemini(all_data, sr_levels=None):
    """Mengubah semua data DataFrame dan S/R menjadi satu laporan teks komprehensif."""
    report = "Berikut adalah data harga OHLCV terbaru untuk dianalisis:\n\n"
    for tf, df in all_data.items():
        if df is not None and not df.empty:
            df_subset = df.copy()
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"--- Data Timeframe: {tf} ---\n"
            report += df_subset.to_string(index=False)
            report += "\n\n"
            
    if sr_levels:
        report += "--- Level Support/Resistance Kunci (Pivot Points Harian) ---\n"
        report += f"Resistance 2 (R2): {sr_levels['R2']:,.2f}\n"
        report += f"Resistance 1 (R1): {sr_levels['R1']:,.2f}\n"
        report += f"Pivot Point (P):   {sr_levels['Pivot']:,.2f}\n"
        report += f"Support 1 (S1):    {sr_levels['S1']:,.2f}\n"
        report += f"Support 2 (S2):    {sr_levels['S2']:,.2f}\n\n"
        
    return report

def get_gemini_analysis(price_data_report):
    """
    Mengirim laporan multi-timeframe ke Gemini dan meminta rencana trading dalam format JSON.
    """
    try:
        print("Menghubungi Google Gemini untuk analisis komprehensif...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json"
        )
        model = genai.GenerativeModel(
            'gemini-1.5-flash-latest',
            generation_config=generation_config
        )
        
        prompt = (
            "Anda adalah seorang trader dan analis teknikal profesional dengan spesialisasi analisis top-down multi-timeframe. "
            f"Tugas Anda adalah menganalisis data harga OHLCV mentah untuk {SYMBOL} yang saya berikan. "
            "Lakukan analisis berikut:\n"
            "1. Identifikasi tren utama dan struktur pasar pada timeframe tinggi (1D, 4H).\n"
            "2. Gunakan level Support/Resistance (Pivot Points) yang disediakan sebagai acuan utama untuk menentukan potensi target profit dan level stop loss.\n"
            "3. Cari potensi area support/resistance kunci lainnya, zona likuiditas, dan pola chart mayor dari data harga.\n"
            "4. Gunakan timeframe rendah (1H, 15M) untuk mencari konfirmasi, momentum, dan sinyal entry yang presisi.\n"
            "5. Rangkum semua temuan Anda ke dalam satu rencana trading yang jelas.\n"
            "Berdasarkan analisis komprehensif Anda, berikan output HANYA dalam format JSON yang valid. "
            "JSON tersebut harus berisi kunci berikut:\n"
            "- 'action': String ('Long', 'Short', atau 'Neutral')\n"
            "- 'entry': Float (harga entri yang disarankan) atau String 'Market' jika entri segera.\n"
            "- 'tp': Float (harga take profit).\n"
            "- 'sl': Float (harga stop loss).\n"
            "- 'reasoning': String (maksimal 2 kalimat singkat yang merangkum alasan utama, misal: 'Tren 1D bullish, 4H membentuk pola bull flag. Entri setelah penembusan di 1H.')\n"
            "Jika tidak ada peluang trading yang jelas, atur 'action' ke 'Neutral' dan nilai numerik lainnya ke 0.\n\n"
            f"Berikut adalah data pasarnya:\n{price_data_report}"
        )
        
        response = model.generate_content(prompt)
        # Membersihkan output sebelum parsing JSON
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
    tp = analysis.get('tp', 0)
    sl = analysis.get('sl', 0)
    reasoning = analysis.get('reasoning', 'Tidak ada alasan spesifik.')

    entry_price_str = f"${entry:,.2f}" if isinstance(entry, (int, float)) else "Market"
    
    if action == 'LONG':
        title = f"📈 **SINYAL AI: LONG {SYMBOL}** 📈"
    elif action == 'SHORT':
        title = f"📉 **SINYAL AI: SHORT {SYMBOL}** 📉"
    else:
        return None

    message = (
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
    return message

def format_status_message(last_price, last_gemini_analysis):
    """Memformat pesan status harian."""
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    reason = last_gemini_analysis.get('reasoning', 'Menunggu peluang trading yang jelas.')
    return (
        f"✅ **Bot Status: OK** ✅\n\n"
        f"Skrip analisis AI berhasil dijalankan pada:\n"
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
        # Memotong pesan jika terlalu panjang untuk Telegram
        if len(message) > 4096:
            message = message[:4090] + "\n..."
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
    
    # --- PERUBAHAN: Mode Debug sekarang mengirim sampel data mentah ---
    if DEBUG_FETCH_ONLY:
        tz = pytz.timezone('Asia/Jakarta')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        
        debug_message = f"⚙️ **Bot Debug: Laporan Data Mentah** ⚙️\n\n"
        debug_message += f"**Waktu:** {now} WIB\n\n"
        
        success_count = 0
        for tf, df in all_market_data.items():
            debug_message += f"--- Timeframe {tf} ---\n"
            if df is not None and not df.empty:
                status = "✅ Berhasil diambil."
                # Mengambil 5 baris terakhir dan format sebagai teks
                sample_data = df.tail(5).copy()
                sample_data['timestamp'] = sample_data['timestamp'].dt.strftime('%m-%d %H:%M')
                data_string = sample_data.to_string(index=False)
                
                debug_message += f"{status}\n"
                debug_message += f"```{data_string}```\n\n" # Menggunakan format code block
                success_count += 1
            else:
                status = "❌ Gagal diambil."
                debug_message += f"{status}\n\n"
            
        if success_count == len(TIMEFRAMES):
            debug_message += "Semua data berhasil diambil. Bot siap untuk analisis."
        else:
            debug_message += "Ada masalah saat mengambil data. Periksa log Actions untuk detail."

        await send_telegram_message(debug_message)
        return # Menghentikan eksekusi setelah mengirim laporan debug

    if all_market_data.get('4h') is None or all_market_data['4h'].empty:
        await send_telegram_message("❌ **Bot Error:** Gagal mengambil data pasar utama (4h). Cek log Actions.")
        return
    last_price = all_market_data['4h']['close'].iloc[-1]

    # Menghitung level S/R dari data harian
    sr_levels = None
    daily_df = all_market_data.get('1d')
    if daily_df is not None and not daily_df.empty:
        sr_levels = calculate_pivot_points(daily_df)

    price_report = format_data_for_gemini(all_market_data, sr_levels)
    analysis_result = get_gemini_analysis(price_report)
    
    if analysis_result is None:
        await send_telegram_message("❌ **Bot Error:** Gagal mendapatkan analisis dari Gemini AI. Cek log Actions.")
        return

    current_action = analysis_result.get('action', 'Neutral').upper()

    if current_action in ["LONG", "SHORT"]:
        last_signal = read_last_signal()
        if current_action != last_signal:
            print(f"Sinyal baru ({current_action}) terdeteksi. Mengirim notifikasi...")
            message = format_signal_message(analysis_result, last_price)
            await send_telegram_message(message)
            write_last_signal(current_action)
            signal_sent = True
        else:
            print(f"Sinyal saat ini ({current_action}) sama dengan yang terakhir dikirim. Tidak ada notifikasi baru.")

    if not signal_sent:
        print("Tidak ada sinyal trading baru. Mengirim pesan status...")
        status_message = format_status_message(last_price, analysis_result)
        await send_telegram_message(status_message)

if __name__ == "__main__":
    asyncio.run(main())

