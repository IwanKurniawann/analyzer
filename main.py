# -*- coding: utf-8 -*-

"""
Skrip utama untuk menganalisis data harga BTC/USDT menggunakan Google Gemini,
dan mengirim notifikasi sinyal trading ke Telegram.
Strategi ini sepenuhnya digerakkan oleh analisis AI.
"""

import os
import sys
import ccxt
import pandas as pd
import asyncio
import telegram
import google.generativeai as genai
from datetime import datetime
import pytz

# --- KONFIGURASI ---
SYMBOL = 'SOL/USDT'
TIMEFRAME = '4h' # Timeframe yang akan dianalisis oleh Gemini
CANDLE_COUNT_FOR_GEMINI = 50 # Jumlah candle terakhir yang akan dikirim ke AI

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
    if not GEMINI_API_KEY:
        print("Error: Pastikan GEMINI_API_KEY sudah diatur di GitHub Secrets.")
        sys.exit(1)

def fetch_data(symbol, timeframe, limit):
    """
    Mengambil data OHLCV dari KuCoin menggunakan ccxt.
    """
    try:
        print(f"Mengambil {limit} data candle terakhir untuk {symbol} pada timeframe {timeframe} dari KuCoin...")
        exchange = ccxt.kucoin() 
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print("Data berhasil diambil.")
        return df
    except Exception as e:
        print(f"Error saat mengambil data dari bursa: {e}")
        return None

def format_data_for_gemini(df):
    """Mengubah data DataFrame menjadi format teks yang bisa dibaca AI."""
    df_subset = df.tail(CANDLE_COUNT_FOR_GEMINI).copy()
    df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
    report = "Berikut adalah data harga OHLCV terbaru dalam format teks:\n\n"
    report += df_subset.to_string(index=False)
    return report

def get_gemini_analysis(price_data_report):
    """
    Mengirim data harga mentah ke Gemini dan meminta sinyal trading.
    """
    try:
        print("Menghubungi Google Gemini untuk analisis pasar...")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = (
            "Anda adalah seorang trader dan analis teknikal profesional dengan pengalaman 20 tahun di pasar cryptocurrency. "
            "Tugas Anda adalah menganalisis data harga OHLCV mentah yang saya berikan untuk pasangan SOL/USDT pada timeframe 4 jam. "
            "Fokus secara mendalam pada price action, pola candlestick yang terbentuk, momentum, volatilitas, serta potensi level support dan resistance kunci. "
            "Berdasarkan analisis komprehensif Anda terhadap data berikut, berikan kesimpulan sinyal trading Anda HANYA dalam satu kata dari daftar berikut: 'STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', atau 'STRONG_SELL'. "
            "Jangan memberikan penjelasan, justifikasi, atau kata-kata lain.\n\n"
            f"{price_data_report}"
        )
        
        response = model.generate_content(prompt)
        result = response.text.strip().upper()
        print(f"Gemini Analysis Result: {result}")

        valid_signals = ['STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG_SELL']
        if result in valid_signals:
            return result
        else:
            print(f"Peringatan: Gemini memberikan respons yang tidak valid: {result}")
            return "NEUTRAL" # Anggap netral jika respons tidak sesuai
            
    except Exception as e:
        print(f"Error saat menghubungi Gemini API: {e}")
        return None

def format_signal_message(signal, current_price):
    """Memformat pesan notifikasi sinyal trading dari AI."""
    if signal == 'STRONG_BUY':
        title = "🚨 **SINYAL AI: STRONG BUY** 🚨"
        emoji = "🚀"
    elif signal == 'STRONG_SELL':
        title = "📉 **SINYAL AI: STRONG SELL** 📉"
        emoji = "💥"
    else:
        # Fungsi ini hanya dipanggil untuk sinyal kuat
        return "Format pesan tidak valid."

    message = (
        f"{title}\n\n"
        f"{emoji} Gemini AI telah mendeteksi sinyal perdagangan kuat untuk **{SYMBOL}**.\n\n"
        f"**Timeframe Analisis:** {TIMEFRAME.upper()}\n"
        f"**Harga Saat Ini:** ${current_price:,.2f}\n\n"
        f"*Disclaimer: Ini bukan nasihat keuangan. Lakukan riset Anda sendiri.*"
    )
    return message

def format_status_message(last_price, last_gemini_signal):
    """Memformat pesan status harian."""
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    return (
        f"✅ **Bot Status: OK** ✅\n\n"
        f"Skrip analisis AI berhasil dijalankan pada:\n"
        f"**Waktu:** {now} WIB\n\n"
        f"**Status Pasar Terakhir:**\n"
        f"  - **Harga {SYMBOL}:** ${last_price:,.2f}\n"
        f"  - **Sinyal AI Terakhir:** {last_gemini_signal}\n\n"
        f"*Tidak ada sinyal trading KUAT yang baru.*"
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
    
    df = fetch_data(SYMBOL, TIMEFRAME, CANDLE_COUNT_FOR_GEMINI)
    if df is None or df.empty:
        await send_telegram_message("❌ **Bot Error:** Gagal mengambil data pasar dari KuCoin. Cek log Actions.")
        return

    last_price = df['close'].iloc[-1]
    
    price_report = format_data_for_gemini(df)
    current_signal = get_gemini_analysis(price_report)
    
    if current_signal is None:
        await send_telegram_message("❌ **Bot Error:** Gagal mendapatkan analisis dari Gemini AI. Cek log Actions.")
        return

    # Hanya kirim notifikasi untuk sinyal yang dianggap kuat
    if current_signal in ["STRONG_BUY", "STRONG_SELL"]:
        last_signal = read_last_signal()
        if current_signal != last_signal:
            print(f"Sinyal kuat baru ({current_signal}) terdeteksi. Mengirim notifikasi...")
            message = format_signal_message(current_signal, last_price)
            await send_telegram_message(message)
            write_last_signal(current_signal)
            signal_sent = True
        else:
            print(f"Sinyal kuat saat ini ({current_signal}) sama dengan yang terakhir dikirim. Tidak ada notifikasi.")

    if not signal_sent:
        print("Tidak ada sinyal kuat baru. Mengirim pesan status...")
        status_message = format_status_message(last_price, current_signal)
        await send_telegram_message(status_message)

if __name__ == "__main__":
    asyncio.run(main())

