# -*- coding: utf-8 -*-
"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif.
Versi ini telah di-refactor dengan prinsip-prinsip clean code untuk
kemudahan pembacaan, pemeliharaan, dan skalabilitas.
Menggunakan Groq API untuk analisis LLM yang cepat.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pandas_ta as ta
import telegram
from openai import AsyncOpenAI
from ccxt.pro import kucoin, Exchange  # Impor exchange secara spesifik

# --- 1. KONFIGURASI & KONSTANTA ---
# Konfigurasi dipisahkan untuk kemudahan pengelolaan.
class Config:
    """Menampung semua konfigurasi aplikasi."""
    SYMBOL: str = 'SOL/USDT'
    TIMEFRAMES: List[str] = ['4h', '1h', '15m']
    EXCHANGE_ID: str = 'kucoin'
    CANDLE_COUNT_FETCH: int = 1000
    FIBONACCI_TIMEFRAME: str = '15m'
    FIBONACCI_SWING_CANDLES: int = 60
    GROQ_MODEL: str = 'llama3-8b-8192'

    INDICATORS: Dict[str, Dict[str, Any]] = {
        'rsi': {'length': 14},
        'ema': {'lengths': [21, 50, 200]},
        'adx': {'length': 14},
        'volume': {'ma_length': 21}
    }

# Kredensial diambil dari environment variables untuk keamanan.
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID: Optional[str] = os.getenv('TELEGRAM_CHAT_ID')
GROQ_API_KEY: Optional[str] = os.getenv('GROQ_API_KEY')

# Prompt untuk AI dipisahkan agar logika utama tetap bersih.
SYSTEM_PROMPT = (
    "PERAN: Anda adalah seorang Certified Financial Technician (CFTe) elit yang "
    "metodis dan logis. Anda hanya membalas dalam format JSON yang valid.\n\n"
    "TUGAS & ATURAN:\n"
    "1. Lakukan analisis multi-timeframe (4H, 1H, 15M) pada data yang diberikan.\n"
    "2. Identifikasi minimal 3 faktor konfluensi.\n"
    "3. Buat satu rencana trading yang logis berdasarkan HARGA SAAT INI.\n"
    "4. 'BUY LIMIT' hanya jika harga entry di bawah harga saat ini. 'SELL LIMIT' "
    "hanya jika harga entry di atas harga saat ini.\n"
    "5. Jika tidak ada setup yang jelas, gunakan 'NEUTRAL' dan jelaskan alasannya.\n"
    "6. Berikan alasan singkat dan jelas untuk setiap rencana trading yang dibuat.\n\n"
    "STRUKTUR JSON OUTPUT:\n"
    '{"analysis": {"h4_trend": "...", "h1_structure": "...", "m15_confirmation": '
    '"...", "confluence_factors": "...", "summary": "..."}, "trade_plan": {"Action": '
    '"...", "Entry": "...", "SL": "...", "TP1": "...", "TP2": "...", "reasoning": "..."}}'
)

# --- 2. LAYANAN & FUNGSI UTILITAS ---
# Fungsi-fungsi dikelompokkan berdasarkan tanggung jawabnya.

# --- Bagian Data Pasar ---
async def fetch_market_data(
    symbol: str, timeframes: List[str], limit: int, exchange_id: str
) -> Dict[str, Optional[pd.DataFrame]]:
    """Mengambil data OHLCV untuk semua timeframe secara konkuren."""
    all_data: Dict[str, Optional[pd.DataFrame]] = {tf: None for tf in timeframes}
    exchange: Exchange = kucoin()  # Inisialisasi exchange
    print(f"Menginisialisasi pengambilan data untuk {symbol} dari {exchange.name}...")

    async def fetch_single(tf: str):
        try:
            print(f"Mengambil {limit} candle terakhir pada timeframe {tf}...")
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            all_data[tf] = df
            print(f"Data untuk {tf} berhasil diambil.")
        except Exception as e:
            print(f"Error saat mengambil data untuk {tf}: {e}")

    try:
        await asyncio.gather(*(fetch_single(tf) for tf in timeframes))
    finally:
        await exchange.close()
        print("Koneksi exchange telah ditutup.")
    return all_data

def calculate_technical_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """Menghitung semua indikator teknis yang dikonfigurasi untuk satu DataFrame."""
    indicators = {}
    cfg = Config.INDICATORS
    try:
        # RSI
        rsi_cfg = cfg.get('rsi')
        if rsi_cfg:
            df.ta.rsi(length=rsi_cfg['length'], append=True)
            indicators['RSI'] = f"{df.iloc[-1].get(f'RSI_{rsi_cfg['length']}', 0):.2f}"

        # EMA
        ema_cfg = cfg.get('ema')
        if ema_cfg:
            ema_values = {}
            for length in ema_cfg['lengths']:
                df.ta.ema(length=length, append=True)
                ema_values[f"EMA_{length}"] = f"{df.iloc[-1].get(f'EMA_{length}', 0):.2f}"
            indicators['EMAs'] = ema_values

        # ADX
        adx_cfg = cfg.get('adx')
        if adx_cfg:
            adx_data = df.ta.adx(length=adx_cfg['length'], append=True)
            adx_value = adx_data.iloc[-1].get(f'ADX_{adx_cfg["length"]}') if adx_data is not None else None
            status = "Tren Kuat" if adx_value and adx_value > 25 else "Tren Lemah / Ranging"
            indicators['ADX'] = {"ADX": f"{adx_value:.2f}" if adx_value else "N/A", "Status": status}

        # Volume
        vol_cfg = cfg.get('volume')
        if vol_cfg:
            vol_ma = df['volume'].rolling(window=vol_cfg['ma_length']).mean()
            status = "Di Atas Rata-rata" if df['volume'].iloc[-1] > vol_ma.iloc[-1] else "Di Bawah Rata-rata"
            indicators['Volume'] = {"Status": status}
    except Exception as e:
        print(f"Peringatan: Gagal menghitung sebagian indikator TA. Error: {e}")
    return indicators

def calculate_fibonacci_levels(df: pd.DataFrame, swing_candles: int) -> Optional[Dict[str, Any]]:
    """Menghitung level Fibonacci Retracement dari swing high/low terakhir."""
    if len(df) < swing_candles: return None
    recent_df = df.tail(swing_candles)
    swing_high, swing_low = recent_df['high'].max(), recent_df['low'].min()
    if swing_high == swing_low: return None
    
    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fibo_levels = {f"{lvl*100:.1f}%": f"{(swing_high - (swing_high - swing_low) * lvl):.4f}" for lvl in levels}
    return {"swing_high": f"{swing_high:.4f}", "swing_low": f"{swing_low:.4f}", "levels": fibo_levels}

# --- Bagian Interaksi AI ---
def format_report_for_ai(all_indicators: Dict[str, Any], fibo_levels: Optional[Dict[str, Any]]) -> str:
    """Menyusun laporan data teks yang ringkas untuk dianalisis oleh AI."""
    report = "Data teknis pasar untuk dianalisis:\n\n--- Ringkasan Indikator Teknis ---\n"
    for tf, indicators in all_indicators.items():
        if not indicators: continue
        report += f"**Timeframe: {tf}**\n"
        parts = []
        if 'RSI' in indicators: parts.append(f"RSI: {indicators['RSI']}")
        if 'EMAs' in indicators: parts.append(f"EMAs: {', '.join(f'{k}: {v}' for k, v in indicators['EMAs'].items())}")
        if 'ADX' in indicators: parts.append(f"ADX: {indicators['ADX']['ADX']} ({indicators['ADX']['Status']})")
        if 'Volume' in indicators: parts.append(f"Volume: {indicators['Volume']['Status']}")
        report += "- " + "\n- ".join(parts) + "\n\n"

    if fibo_levels:
        report += (f"--- Fibonacci Retracement {Config.FIBONACCI_TIMEFRAME} "
                   f"(L: ${fibo_levels['swing_low']}, H: ${fibo_levels['swing_high']}) ---\n")
        report += "\n".join(f"Level {level}: ${price}" for level, price in fibo_levels['levels'].items()) + "\n\n"
    return report

async def get_ai_analysis(report: str, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
    """Mengirim laporan ke Groq dan mengembalikan hasil analisis dalam format JSON."""
    if not GROQ_API_KEY: return None
    print(f"Menghubungi Groq ({Config.GROQ_MODEL}) untuk analisis...")
    try:
        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)
        user_prompt = (
            f"ASET: {symbol}\nKONTEKS HARGA SAAT INI: ${current_price:,.4f}\n\n"
            f"DATA TEKNIS:\n{report}\n\nLakukan analisis dan hasilkan JSON sesuai aturan."
        )
        response = await client.chat.completions.create(
            model=Config.GROQ_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
        )
        analysis = json.loads(response.choices[0].message.content)
        print("Analisis dari Groq berhasil diterima.")
        return analysis
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons Groq: {e}")
        return None

# --- Bagian Notifikasi ---
def format_telegram_message(analysis: Dict[str, Any], symbol: str, current_price: float) -> str:
    """Memformat hasil analisis menjadi pesan yang siap dikirim ke Telegram."""
    analisis_data = analysis.get('analysis', {})
    trade_plan = analysis.get('trade_plan', {})
    action = trade_plan.get('Action', 'NEUTRAL').upper()

    emoji_map = {'BUY': ('🟢', '📈'), 'SELL': ('🔴', '📉'), 'NEUTRAL': ('⚪️', '➡️')}
    main_emoji, bias_emoji = emoji_map.get(action.split()[0], emoji_map['NEUTRAL'])
    
    header = f"*{main_emoji} ANALISIS TEKNIKAL CFTe UNTUK {symbol} {bias_emoji}*\n\n*Harga Saat Ini: ${current_price:,.4f}*\n"
    separator = "----------------------------------------\n\n"
    
    analysis_section = (
        f"*Analisis Multi-Timeframe:*\n\n"
        f"🕓 *4 Jam (Tren & Kekuatan):* _{analisis_data.get('h4_trend', 'N/A')}_\n"
        f"🕐 *1 Jam (Struktur & Volume):* _{analisis_data.get('h1_structure', 'N/A')}_\n"
        f"⏱️ *15 Menit (Konfirmasi Entri):* _{analisis_data.get('m15_confirmation', 'N/A')}_\n\n"
        f"*🎯 Konfluensi Sinyal Utama:*\n_{analisis_data.get('confluence_factors', 'N/A')}_\n\n"
    )

    plan_header = f"📌 *SINTESIS & RENCANA TRADING*\n\n*{analisis_data.get('summary', 'N/A')}*\n\n"
    plan_details = ""
    if action != 'NEUTRAL':
        plan_details = (
            f"  - *Aksi:* {action}\n"
            f"  - *Area Entry:* {trade_plan.get('Entry', 'N/A')}\n"
            f"  - *Take Profit 1:* {trade_plan.get('TP1', 'N/A')}\n"
            f"  - *Take Profit 2:* {trade_plan.get('TP2', 'N/A')}\n"
            f"  - *Stop Loss:* {trade_plan.get('SL', 'N/A')}\n\n"
        )
    
    reasoning = f"*🧠 Alasan Rencana:* _{trade_plan.get('reasoning', 'N/A')}_\n\n"
    footer = "*Disclaimer: Ini adalah analisis otomatis dan bukan nasihat keuangan.*"

    return f"{header}{separator}{analysis_section}{separator}{plan_header}{plan_details}{reasoning}{footer}"

async def send_telegram_notification(message: str):
    """Mengirim pesan notifikasi ke channel Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        # Menangani pesan yang terlalu panjang
        if len(message) > 4096:
            message = message[:4090] + "\n[...]"
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Notifikasi analisis berhasil dikirim ke Telegram.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")


# --- 3. ALUR KERJA UTAMA ---
def validate_credentials():
    """Memvalidasi keberadaan semua kredensial yang dibutuhkan."""
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY]):
        missing = [
            cred for cred, val in 
            [("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN), 
             ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID), 
             ("GROQ_API_KEY", GROQ_API_KEY)] 
            if not val
        ]
        sys.exit(f"Error: Kredensial berikut belum diatur: {', '.join(missing)}")

async def run_analysis_pipeline():
    """Menjalankan seluruh alur proses analisis dari awal hingga akhir."""
    validate_credentials()
    
    market_data = await fetch_market_data(
        Config.SYMBOL, Config.TIMEFRAMES, Config.CANDLE_COUNT_FETCH, Config.EXCHANGE_ID
    )

    valid_data = {tf: df for tf, df in market_data.items() if df is not None and not df.empty}
    if len(valid_data) != len(Config.TIMEFRAMES):
        failed_tfs = set(Config.TIMEFRAMES) - set(valid_data.keys())
        await send_telegram_notification(f"❌ **Bot Error:** Gagal mengambil data pasar untuk: {', '.join(failed_tfs)}.")
        return
        
    current_price = valid_data[Config.TIMEFRAMES[-1]]['close'].iloc[-1]
    
    all_indicators = {tf: calculate_technical_indicators(df) for tf, df in valid_data.items()}
    
    fibo_df = valid_data.get(Config.FIBONACCI_TIMEFRAME)
    fibo_levels = calculate_fibonacci_levels(fibo_df, Config.FIBONACCI_SWING_CANDLES) if fibo_df is not None else None
    
    technical_report = format_report_for_ai(all_indicators, fibo_levels)
    
    ai_analysis = await get_ai_analysis(technical_report, Config.SYMBOL, current_price)
    
    if not ai_analysis:
        await send_telegram_notification(f"❌ **Bot Error:** Gagal mendapatkan analisis dari AI untuk {Config.SYMBOL}.")
        return

    report_message = format_telegram_message(ai_analysis, Config.SYMBOL, current_price)
    await send_telegram_notification(report_message)

if __name__ == "__main__":
    try:
        asyncio.run(run_analysis_pipeline())
    except KeyboardInterrupt:
        print("\nProses dihentikan oleh pengguna.")
