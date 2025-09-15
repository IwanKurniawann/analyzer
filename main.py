# -*- coding: utf-8 -*-
"""
main.py

Skrip ini mengimplementasikan strategi trading "Strong Engulfing/Reversal Strategy v8"
berdasarkan logika Pine Script yang diberikan.
- Mengambil data OHLCV dari KuCoin menggunakan CCXT.
- Menghitung indikator teknis (SMA, RSI, ATR) menggunakan Pandas TA.
- Menerapkan sistem skor untuk mengidentifikasi sinyal beli.
- Mengirim notifikasi sinyal ke Telegram.
- (Opsional) Terintegrasi dengan Gemini API untuk analisis lebih lanjut.
"""

import os
import asyncio
import logging
import pandas as pd
import pandas_ta as ta
import ccxt.async_support as ccxt
from telegram import Bot
from dotenv import load_dotenv

# --- KONFIGURASI ---
# Muat environment variables dari file .env (opsional, untuk pengembangan lokal)
load_dotenv()

# Konfigurasi Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ambil kredensial dari environment variables (lebih aman untuk produksi/GitHub Actions)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Kredensial KuCoin (opsional, hanya diperlukan untuk trading, tidak untuk data publik)
# KUCOIN_API_KEY = os.getenv('KUCOIN_API_KEY')
# KUCOIN_SECRET = os.getenv('KUCOIN_SECRET')
# KUCOIN_PASSWORD = os.getenv('KUCOIN_PASSWORD')

# (Opsional) Kunci API Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- PARAMETER STRATEGI ---
# Pengaturan yang bisa diubah sesuai kebutuhan
PAIRS_TO_CHECK = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
TIMEFRAME = '15m'  # Timeframe candle (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
CANDLE_LIMIT = 200 # Jumlah candle yang akan diambil

# Input Strategi (sesuai Pine Script)
BUY_THRESHOLD = 3
BODY_MULTIPLIER = 1.1
TREND_SMA_LENGTH = 50
RSI_LENGTH = 14
ATR_LENGTH = 14
TP_PERC = 3.0
SL_PERC = 1.5


async def send_telegram_message(message: str):
    """Mengirim pesan ke channel atau grup Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Token atau Chat ID Telegram tidak diatur. Pesan tidak terkirim.")
        print(f"TELEGRAM DEBUG: {message}")
        return
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        logging.info(f"Pesan berhasil dikirim ke Telegram.")
    except Exception as e:
        logging.error(f"Gagal mengirim pesan ke Telegram: {e}")

async def get_kucoin_data(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Mengambil data OHLCV dari KuCoin."""
    exchange = ccxt.kucoin() # Tidak perlu otentikasi untuk data publik
    try:
        logging.info(f"Mengambil data untuk {symbol} pada timeframe {timeframe}...")
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        logging.error(f"Gagal mengambil data dari KuCoin untuk {symbol}: {e}")
        return pd.DataFrame()
    finally:
        await exchange.close()

def calculate_indicators(df: pd.DataFrame):
    """Menghitung indikator teknis yang dibutuhkan."""
    if df.empty:
        return df
    df.ta.sma(length=TREND_SMA_LENGTH, append=True)
    df.ta.rsi(length=RSI_LENGTH, append=True)
    df.ta.atr(length=ATR_LENGTH, append=True)
    return df

def check_strategy_conditions(df: pd.DataFrame) -> (int, dict):
    """Menerapkan logika skor berdasarkan kondisi strategi."""
    if len(df) < 2:
        return 0, {}

    # Analisis pada candle terakhir yang sudah selesai (indeks -2)
    # Indeks -1 adalah candle saat ini yang belum tentu selesai
    last_closed_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]

    bullish_score = 0
    conditions_met = {}

    # 1. Skor Pola Candlestick (Bobot: 2 Poin)
    body_size = abs(last_closed_candle['close'] - last_closed_candle['open'])
    prev_body_size = abs(prev_candle['close'] - prev_candle['open'])
    
    is_bullish_engulfing = (
        prev_candle['close'] < prev_candle['open'] and  # Candle sebelumnya bearish
        last_closed_candle['close'] > last_closed_candle['open'] and # Candle saat ini bullish
        last_closed_candle['open'] < prev_candle['close'] and
        last_closed_candle['close'] > prev_candle['open'] and
        body_size > prev_body_size * BODY_MULTIPLIER
    )
    if is_bullish_engulfing:
        bullish_score += 2
        conditions_met['Pola'] = "Bullish Engulfing"

    # 2. Skor Tren (Bobot: 1 Poin)
    sma_col = f'SMA_{TREND_SMA_LENGTH}'
    if last_closed_candle['close'] > last_closed_candle[sma_col]:
        bullish_score += 1
        conditions_met['Tren'] = f"Harga di atas SMA {TREND_SMA_LENGTH}"

    # 3. Skor Momentum (Bobot: 1 Poin)
    rsi_col = f'RSI_{RSI_LENGTH}'
    if last_closed_candle[rsi_col] > 55:
        bullish_score += 1
        conditions_met['Momentum'] = f"RSI({RSI_LENGTH}) > 55 ({last_closed_candle[rsi_col]:.2f})"

    # 4. Skor Volatilitas (Bobot: 1 Poin)
    atr_col = f'ATRr_{ATR_LENGTH}'
    if last_closed_candle[atr_col] > prev_candle[atr_col]:
        bullish_score += 1
        conditions_met['Volatilitas'] = "ATR Meningkat"
        
    return bullish_score, conditions_met

async def get_gemini_analysis(prompt: str) -> str:
    """(Opsional) Mendapatkan analisis dari Google Gemini API."""
    if not GEMINI_API_KEY:
        return "Analisis Gemini tidak tersedia (API Key tidak diatur)."
    
    try:
        # Import library hanya jika akan digunakan
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except Exception as e:
        logging.error(f"Error saat menghubungi Gemini API: {e}")
        return "Gagal mendapatkan analisis dari Gemini."

async def main():
    """Fungsi utama untuk menjalankan scanner."""
    logging.info("Memulai proses pemindaian sinyal...")

    for pair in PAIRS_TO_CHECK:
        # 1. Ambil data
        df = await get_kucoin_data(pair, TIMEFRAME, CANDLE_LIMIT)
        if df.empty:
            logging.warning(f"Tidak ada data untuk {pair}, melanjutkan ke pair berikutnya.")
            continue

        # 2. Hitung Indikator
        df = calculate_indicators(df)

        # 3. Periksa Kondisi Strategi
        score, conditions = check_strategy_conditions(df)
        
        logging.info(f"[{pair}] Skor Bullish: {score}/{BUY_THRESHOLD}")

        # 4. Kirim Notifikasi jika ambang batas tercapai
        if score >= BUY_THRESHOLD:
            last_price = df.iloc[-2]['close']
            tp_price = last_price * (1 + TP_PERC / 100)
            sl_price = last_price * (1 - SL_PERC / 100)
            
            # Buat pesan notifikasi
            message_lines = [
                f"🚨 *SINYAL BELI TERDETEKSI* 🚨",
                f" cặp tiền tệ: *{pair}*",
                f"Timeframe: *{TIMEFRAME}*",
                f"Harga Saat Ini: `{last_price}`",
                f"Skor Bullish: *{score}* (Ambang Batas: {BUY_THRESHOLD})",
                "\n*Kondisi yang Terpenuhi:*",
            ]
            for cond, desc in conditions.items():
                message_lines.append(f"- *{cond}*: {desc}")

            message_lines.extend([
                "\n*Manajemen Risiko:*",
                f"- ✅ Take Profit: `{tp_price:.4f}` ({TP_PERC}%)",
                f"- ❌ Stop Loss: `{sl_price:.4f}` ({SL_PERC}%)"
            ])

            # (Opsional) Tambahkan analisis dari Gemini
            # gemini_prompt = (
            #     f"Analisis singkat kondisi pasar saat ini untuk {pair} (timeframe {TIMEFRAME}). "
            #     f"Sinyal beli terdeteksi dengan kondisi: {', '.join(conditions.values())}. "
            #     f"Apakah ada berita atau sentimen pasar penting yang perlu diperhatikan?"
            # )
            # gemini_insight = await get_gemini_analysis(gemini_prompt)
            # message_lines.append(f"\n*🤖 Analisis Gemini:* \n_{gemini_insight}_")

            final_message = "\n".join(message_lines)
            await send_telegram_message(final_message)
        else:
            logging.info(f"[{pair}] Tidak ada sinyal beli yang memenuhi syarat.")
            
    logging.info("Proses pemindaian selesai.")

if __name__ == "__main__":
    # Pastikan token dan chat ID ada sebelum menjalankan
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Harap atur TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di environment variables.")
    else:
        asyncio.run(main())
