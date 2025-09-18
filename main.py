# -*- coding: utf-8 -*-
"""
main.py

Skrip ini mengimplementasikan strategi trading "Strong Engulfing/Reversal Strategy v8"
untuk sinyal BELI (LONG) dan JUAL (SHORT) yang diperkuat dengan deteksi Golden/Death Cross.
- Mengambil data OHLCV dari KuCoin menggunakan CCXT.
- Menghitung indikator teknis (SMA, RSI, ATR) menggunakan Pandas TA.
- Menerapkan sistem skor untuk mengidentifikasi sinyal beli dan jual.
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

# (Opsional) Kunci API Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- PARAMETER STRATEGI ---
# Pengaturan yang bisa diubah sesuai kebutuhan
PAIRS_TO_CHECK = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'LINK/USDT', 'ONDO/USDT']
TIMEFRAME = '15m'  # Timeframe candle (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
CANDLE_LIMIT = 201 # Butuh 201 candle untuk menghitung SMA 200 dengan benar

# Input Strategi (sesuai Pine Script)
BUY_THRESHOLD = 5  # Ambang batas skor untuk sinyal Beli
SELL_THRESHOLD = 5  # Ambang batas skor untuk sinyal Jual
BODY_MULTIPLIER = 1.1
LONG_SMA_LENGTH = 200   # Untuk tren jangka panjang & Death/Golden Cross
SHORT_SMA_LENGTH = 50   # Untuk tren jangka menengah & Death/Golden Cross
RSI_LENGTH = 14
ATR_LENGTH = 14
TP_PERC = 4.8
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
        logging.info("Pesan berhasil dikirim ke Telegram.")
    except Exception as e:
        logging.error(f"Gagal mengirim pesan ke Telegram: {e}")

async def get_kucoin_data(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Mengambil data OHLCV dari KuCoin."""
    exchange = ccxt.kucoin()
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
    df.ta.sma(length=SHORT_SMA_LENGTH, append=True)
    df.ta.sma(length=LONG_SMA_LENGTH, append=True)
    df.ta.rsi(length=RSI_LENGTH, append=True)
    df.ta.atr(length=ATR_LENGTH, append=True)
    return df

def analyze_market_conditions(df: pd.DataFrame) -> (int, dict, int, dict):
    """
    Menerapkan logika skor untuk sinyal LONG dan SHORT.
    Mengembalikan skor dan kondisi untuk bullish dan bearish.
    """
    if len(df) < 3:
        return 0, {}, 0, {}

    last_closed_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]

    bullish_score, bearish_score = 0, 0
    bullish_conditions, bearish_conditions = {}, {}

    # --- Analisis Umum ---
    body_size = abs(last_closed_candle['close'] - last_closed_candle['open'])
    prev_body_size = abs(prev_candle['close'] - prev_candle['open'])
    short_sma_col = f'SMA_{SHORT_SMA_LENGTH}'
    long_sma_col = f'SMA_{LONG_SMA_LENGTH}'
    rsi_col = f'RSI_{RSI_LENGTH}'
    atr_col = f'ATRr_{ATR_LENGTH}'

    # --- LOGIKA UNTUK SINYAL BELI (BULLISH) ---

    # 1. Skor Pola Candlestick Bullish (Bobot: 2 Poin)
    is_bullish_engulfing = (
        prev_candle['close'] < prev_candle['open'] and
        last_closed_candle['close'] > last_closed_candle['open'] and
        last_closed_candle['open'] < prev_candle['close'] and
        last_closed_candle['close'] > prev_candle['open'] and
        body_size > prev_body_size * BODY_MULTIPLIER
    )
    if is_bullish_engulfing:
        bullish_score += 2
        bullish_conditions['Pola'] = "Bullish Engulfing"

    # 2. Skor Tren Bullish (Bobot: 1 Poin)
    if last_closed_candle['close'] > last_closed_candle[long_sma_col]:
        bullish_score += 1
        bullish_conditions['Tren'] = f"Harga di atas SMA {LONG_SMA_LENGTH}"

    # 3. Skor Momentum Bullish (Bobot: 1 Poin)
    if last_closed_candle[rsi_col] > 55:
        bullish_score += 1
        bullish_conditions['Momentum'] = f"RSI({RSI_LENGTH}) > 55 ({last_closed_candle[rsi_col]:.2f})"

    # 4. Skor Volatilitas (Bobot: 1 Poin - Berlaku untuk keduanya)
    if last_closed_candle[atr_col] > prev_candle[atr_col]:
        bullish_score += 1
        bullish_conditions['Volatilitas'] = "ATR Meningkat"
        bearish_score += 1 # Volatilitas tinggi baik untuk long maupun short
        bearish_conditions['Volatilitas'] = "ATR Meningkat"

    # 5. Skor Golden Cross (Bobot: 2 Poin)
    sma50_now = last_closed_candle[short_sma_col]
    sma200_now = last_closed_candle[long_sma_col]
    sma50_prev = prev_candle[short_sma_col]
    sma200_prev = prev_candle[long_sma_col]

    if sma50_now > sma200_now and sma50_prev <= sma200_prev:
        bullish_score += 2
        bullish_conditions['Cross'] = f"Golden Cross (SMA {SHORT_SMA_LENGTH} > SMA {LONG_SMA_LENGTH})"

    # --- LOGIKA UNTUK SINYAL JUAL (BEARISH) ---

    # 1. Skor Pola Candlestick Bearish (Bobot: 2 Poin)
    is_bearish_engulfing = (
        prev_candle['close'] > prev_candle['open'] and
        last_closed_candle['close'] < last_closed_candle['open'] and
        last_closed_candle['open'] > prev_candle['close'] and
        last_closed_candle['close'] < prev_candle['open'] and
        body_size > prev_body_size * BODY_MULTIPLIER
    )
    if is_bearish_engulfing:
        bearish_score += 2
        bearish_conditions['Pola'] = "Bearish Engulfing"

    # 2. Skor Tren Bearish (Bobot: 1 Poin)
    if last_closed_candle['close'] < last_closed_candle[long_sma_col]:
        bearish_score += 1
        bearish_conditions['Tren'] = f"Harga di bawah SMA {LONG_SMA_LENGTH}"

    # 3. Skor Momentum Bearish (Bobot: 1 Poin)
    if last_closed_candle[rsi_col] < 45:
        bearish_score += 1
        bearish_conditions['Momentum'] = f"RSI({RSI_LENGTH}) < 45 ({last_closed_candle[rsi_col]:.2f})"

    # 4. Skor Death Cross (Bobot: 2 Poin)
    if sma50_now < sma200_now and sma50_prev >= sma200_prev:
        bearish_score += 2
        bearish_conditions['Cross'] = f"Death Cross (SMA {SHORT_SMA_LENGTH} < SMA {LONG_SMA_LENGTH})"

    return bullish_score, bullish_conditions, bearish_score, bearish_conditions

async def get_gemini_analysis(prompt: str) -> str:
    """(Opsional) Mendapatkan analisis dari Google Gemini API."""
    if not GEMINI_API_KEY:
        return "Analisis Gemini tidak tersedia (API Key tidak diatur)."
    
    try:
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
        df = await get_kucoin_data(pair, TIMEFRAME, CANDLE_LIMIT)
        if df.empty or df.isnull().values.any():
            logging.warning(f"Tidak ada data atau data tidak valid untuk {pair}, melanjutkan.")
            continue

        df = calculate_indicators(df)

        bullish_score, bullish_cond, bearish_score, bearish_cond = analyze_market_conditions(df)
        
        logging.info(f"[{pair}] Skor Bullish: {bullish_score}/{BUY_THRESHOLD} | Skor Bearish: {bearish_score}/{SELL_THRESHOLD}")

        last_price = df.iloc[-2]['close']

        # --- Cek Sinyal Beli ---
        if bullish_score >= BUY_THRESHOLD:
            tp_price = last_price * (1 + TP_PERC / 100)
            sl_price = last_price * (1 - SL_PERC / 100)
            
            message_lines = [
                f"🚨 *SINYAL BELI (LONG) TERDETEKSI* 🚨",
                f"Pair: *{pair}*",
                f"Timeframe: *{TIMEFRAME}*",
                f"Harga Saat Ini: `{last_price}`",
                f"Skor Bullish: *{bullish_score}* (Ambang Batas: {BUY_THRESHOLD})",
                "\n*Kondisi yang Terpenuhi:*",
            ]
            for cond, desc in bullish_cond.items():
                message_lines.append(f"- *{cond}*: {desc}")

            message_lines.extend([
                "\n*Manajemen Risiko:*",
                f"- ✅ Take Profit: `{tp_price:.4f}` ({TP_PERC}%)",
                f"- ❌ Stop Loss: `{sl_price:.4f}` ({SL_PERC}%)"
            ])
            
            final_message = "\n".join(message_lines)
            await send_telegram_message(final_message)

        # --- Cek Sinyal Jual ---
        elif bearish_score >= SELL_THRESHOLD:
            tp_price = last_price * (1 - TP_PERC / 100)
            sl_price = last_price * (1 + SL_PERC / 100)
            
            message_lines = [
                f"📉 *SINYAL JUAL (SHORT) TERDETEKSI* 📉",
                f"Pair: *{pair}*",
                f"Timeframe: *{TIMEFRAME}*",
                f"Harga Saat Ini: `{last_price}`",
                f"Skor Bearish: *{bearish_score}* (Ambang Batas: {SELL_THRESHOLD})",
                "\n*Kondisi yang Terpenuhi:*",
            ]
            for cond, desc in bearish_cond.items():
                message_lines.append(f"- *{cond}*: {desc}")

            message_lines.extend([
                "\n*Manajemen Risiko:*",
                f"- ✅ Take Profit: `{tp_price:.4f}` ({TP_PERC}%)",
                f"- ❌ Stop Loss: `{sl_price:.4f}` ({SL_PERC}%)"
            ])

            final_message = "\n".join(message_lines)
            await send_telegram_message(final_message)
        else:
            logging.info(f"[{pair}] Tidak ada sinyal trading yang memenuhi syarat.")
            
    logging.info("Proses pemindaian selesai.")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Harap atur TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di environment variables.")
    else:
        asyncio.run(main())


