
# -*- coding: utf-8 -*-
"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif.
Versi ini telah dimigrasikan dari Google Gemini ke OpenAI GPT API.

Perubahan Utama (v4 - OpenAI Integration):
- Mengganti pustaka 'google.generativeai' menjadi 'openai'.
- Mengubah fungsi `get_gemini_analysis` menjadi `get_openai_analysis`
  dengan logika pemanggilan API yang sepenuhnya baru.
- Menambahkan kredensial baru `OPENAI_API_KEY`.
- Memperbarui `CONFIG` untuk menggunakan model OpenAI (misal: gpt-4o).
- Memisahkan prompt menjadi 'system' (peran & aturan) dan 'user' (data & tugas)
  sesuai format standar OpenAI.
"""

import os
import sys
import ccxt.pro as ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import telegram
import openai # Pustaka baru untuk OpenAI
import json
from datetime import datetime
import pytz

# --- 1. KONFIGURASI UTAMA (MEMBUAT KODE ADAPTIF) ---
# Ubah semua pengaturan di sini.
CONFIG = {
    'symbol': 'SOL/USDT',
    'timeframes': ['4h', '1h', '15m'],
    'exchange_id': 'kucoin',  # Ganti ke 'binance', 'bybit', dll. (case-insensitive)
    'candle_count_for_fetch': 1000,
    'indicators': {
        'rsi': {'length': 14},
        'ema': {'lengths': [21, 50, 200]},
        'adx': {'length': 14},
        'volume_profile': {'ma_length': 21}
    },
    'fibonacci_timeframe': '15m',
    'fibonacci_swing_candles': 60,
    # Model AI diganti ke OpenAI. GPT-5 belum rilis, gpt-4o adalah model terkuat saat ini.
    'openai_model': 'gpt-4o' 
}

# --- KREDENSIAL ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') # Kredensial baru untuk OpenAI

def check_credentials():
    """Memeriksa apakah semua kredensial yang dibutuhkan tersedia."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        sys.exit("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
    if not OPENAI_API_KEY:
        sys.exit("Error: Pastikan OPENAI_API_KEY sudah diatur.")

async def fetch_all_data(symbol, timeframes, limit, exchange_id):
    """
    Mengambil data OHLCV untuk semua timeframe secara konkuren menggunakan ccxt.pro.
    """
    all_data = {}
    exchange = None
    try:
        exchange_class = getattr(ccxt, exchange_id.lower())
        exchange = exchange_class()
    except (AttributeError, ccxt.ExchangeNotFound):
        print(f"Error: Exchange '{exchange_id}' tidak ditemukan atau tidak didukung oleh CCXT Pro.")
        return None

    print(f"Menginisialisasi pengambilan data untuk {symbol} dari {exchange_id.title()}...")

    async def fetch_single_timeframe(tf):
        try:
            print(f"Mengambil {limit} data candle terakhir pada timeframe {tf}...")
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            all_data[tf] = df
            print(f"Data untuk {tf} berhasil diambil.")
        except Exception as e:
            print(f"Error saat mengambil data untuk {tf}: {e}")
            all_data[tf] = None

    await asyncio.gather(*(fetch_single_timeframe(tf) for tf in timeframes))

    if exchange:
        await exchange.close()
        print("Koneksi exchange telah ditutup.")
        
    return all_data

def calculate_ta_indicators(df, indicator_config):
    """
    Menghitung indikator teknis secara dinamis berdasarkan konfigurasi.
    """
    if df is None or df.empty: return None
    
    indicators = {}
    latest = df.iloc[-1]

    try:
        # RSI
        if 'rsi' in indicator_config:
            rsi_length = indicator_config['rsi']['length']
            df.ta.rsi(length=rsi_length, append=True)
            indicators['RSI'] = f"{df.iloc[-1].get(f'RSI_{rsi_length}', 0):.2f}"

        # EMAs
        if 'ema' in indicator_config:
            ema_lengths = indicator_config['ema']['lengths']
            ema_values = {}
            for period in ema_lengths:
                df.ta.ema(length=period, append=True)
                ema_values[f"EMA_{period}"] = f"{df.iloc[-1].get(f'EMA_{period}', 0):.2f}"
            indicators['EMAs'] = ema_values

        # ADX
        if 'adx' in indicator_config:
            adx_length = indicator_config['adx']['length']
            adx_data = df.ta.adx(length=adx_length, append=True)
            if adx_data is not None and not adx_data.empty:
                adx_value = adx_data.iloc[-1].get(f'ADX_{adx_length}')
                if adx_value is not None:
                    indicators['ADX'] = {
                        "ADX": f"{adx_value:.2f}",
                        "Status": "Tren Kuat" if adx_value > 25 else "Tren Lemah / Ranging"
                    }
                else:
                    indicators['ADX'] = {"ADX": "N/A", "Status": "Gagal dihitung"}

        # Analisis Volume
        if 'volume_profile' in indicator_config:
            vol_ma_len = indicator_config['volume_profile']['ma_length']
            vol_ma = df['volume'].rolling(window=vol_ma_len).mean()
            last_vol = latest['volume']
            last_vol_ma = vol_ma.iloc[-1]
            status = "Di Atas Rata-rata" if last_vol > last_vol_ma else "Di Bawah Rata-rata"
            indicators['Volume'] = { "Status": status }

        return indicators
    except Exception as e:
        print(f"Peringatan: Gagal menghitung beberapa indikator TA. Error: {e}")
        return indicators if indicators else None

def calculate_fibonacci_retracement(df, swing_candles):
    """Menghitung Fibonacci Retracement pada swing terakhir."""
    if df is None or len(df) < swing_candles: return None
    
    recent_df = df.tail(swing_candles)
    swing_high = recent_df['high'].max()
    swing_low = recent_df['low'].min()
    
    if swing_high == swing_low: return None

    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fibo_levels = {f"{level*100:.1f}%": f"{(swing_high - (swing_high - swing_low) * level):.4f}" for level in levels}
        
    return {
        "swing_high": f"{swing_high:.4f}",
        "swing_low": f"{swing_low:.4f}",
        "levels": fibo_levels
    }

def format_data_for_gemini(all_data, all_ta_indicators, fibo_levels):
    """Mengubah data teknis menjadi laporan teks yang terstruktur untuk AI."""
    report = "Data teknis pasar untuk dianalisis:\n\n"
    
    report += "--- Ringkasan Indikator Teknis (Nilai Terakhir) ---\n"
    for tf, indicators in all_ta_indicators.items():
        if not indicators: continue
        
        report += f"**Timeframe: {tf}**\n"
        if 'RSI' in indicators: report += f"- RSI: {indicators['RSI']}\n"
        if 'EMAs' in indicators:
            emas_str = ", ".join([f"{k}: {v}" for k, v in indicators['EMAs'].items()])
            report += f"- EMAs: {emas_str}\n"
        if 'ADX' in indicators: report += f"- ADX: {indicators['ADX']['ADX']} ({indicators['ADX']['Status']})\n"
        if 'Volume' in indicators: report += f"- Volume: {indicators['Volume']['Status']}\n"
        report += "\n"

    if fibo_levels:
        report += f"--- Fibonacci Retracement dari Swing {CONFIG['fibonacci_timeframe']} (Swing Low: ${fibo_levels['swing_low']}, Swing High: ${fibo_levels['swing_high']}) ---\n"
        for level, price in fibo_levels['levels'].items():
            report += f"Level {level}: ${price}\n"
        report += "\n"
        
    report += "--- Data Harga Mentah (10 Candle Terakhir untuk Konteks) ---\n"
    for tf, df in all_data.items():
        if df is not None and not df.empty:
            df_subset = df.copy().tail(10)
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"Data Timeframe: {tf}\n"
            report += df_subset[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_string(index=False)
            report += "\n\n"
            
    return report

async def get_openai_analysis(technical_data_report, symbol, model_name, current_price):
    """
    Mengirim laporan teknis ke OpenAI GPT dan meminta analisis.
    Fungsi ini sepenuhnya menggantikan `get_gemini_analysis`.
    """
    try:
        print(f"Menghubungi OpenAI GPT ({model_name}) untuk analisis...")
        # Menggunakan client async untuk integrasi dengan asyncio
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        # Pisahkan prompt menjadi 'system' (peran & aturan) dan 'user' (tugas & data)
        system_prompt = (
            "PERAN: Anda adalah seorang Certified Financial Technician (CFTe) elit. Analisis Anda tajam, metodis, dan selalu logis secara kontekstual.\n\n"
            "TUGAS:\n"
            "1.  **Analisis Multi-Timeframe:** Lakukan analisis top-down (4H, 1H, 15M) dengan fokus pada tren (EMA), kekuatan (ADX), struktur, volume, dan konfirmasi (RSI, candle).\n"
            "2.  **Sintesis & Konfluensi:** Sebutkan minimal 3 faktor teknikal yang bertemu (konfluensi) yang mendukung skenario tradingmu.\n"
            "3.  **Ringkasan Analisis:** Berikan kesimpulan analisis dalam satu kalimat yang padat dan jelas.\n"
            "4.  **Rencana Trading (WAJIB LOGIS):** Buat satu rencana trading berdasarkan analisismu dan HARGA SAAT INI. Ikuti aturan ketat ini:\n"
            "    -   Jika skenario adalah **BUY (Long)** dan area entry idealmu berada **DI BAWAH HARGA SAAT INI**, gunakan **'BUY LIMIT'**.\n"
            "    -   Jika skenario adalah **SELL (Short)** dan area entry idealmu berada **DI ATAS HARGA SAAT INI**, gunakan **'SELL LIMIT'**.\n"
            "    -   Jika tidak ada setup high-probability, set 'Action' ke **'NEUTRAL'** dan jelaskan alasannya di 'reasoning'. JANGAN MEMAKSAKAN TRADE.\n"
            "    -   **Stop Loss (SL)** dan **Take Profit (TP)** harus logis berdasarkan struktur pasar.\n"
            "    -   **Reasoning:** Jelaskan secara singkat mengapa Anda memilih 'Action' dan 'Entry' tersebut.\n\n"
            "FORMAT OUTPUT: Berikan output HANYA dalam format JSON yang valid. WAJIB ISI SEMUA KUNCI. Gunakan struktur berikut:\n"
            "{\n"
            '  "analysis": {"h4_trend": "...", "h1_structure": "...", "m15_confirmation": "...", "confluence_factors": "...", "summary": "..."},\n'
            '  "trade_plan": {"Action": "BUY LIMIT / SELL LIMIT / NEUTRAL", "Entry": "...", "SL": "...", "TP1": "...", "TP2": "...", "reasoning": "..."}\n'
            "}"
        )

        user_prompt = (
             f"ASET: {symbol}\n\n"
            f"KONTEKS:\n**HARGA SAAT INI: ${current_price:,.4f}**\n\n"
            "DATA TEKNIS YANG DISEDIAKAN:\n"
            f"{technical_data_report}\n\n"
            "Lakukan analisis dan buat rencana trading sesuai dengan peran dan aturan yang telah ditetapkan."
        )
        
        response = await client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"}, # Meminta output JSON
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # Ekstrak konten dari respons OpenAI
        analysis_content = response.choices[0].message.content
        analysis = json.loads(analysis_content)
        print("Analisis dari OpenAI berhasil diterima dan diproses.")
        return analysis
            
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons OpenAI: {e}")
        return None

def format_analysis_message(analysis, symbol, current_price):
    """Memformat pesan notifikasi analisis teknikal dari AI."""
    analisis = analysis.get('analysis', {})
    trade_plan = analysis.get('trade_plan', {})
    action = trade_plan.get('Action', 'NEUTRAL').upper()
    
    if 'BUY' in action: main_emoji, bias_emoji = '🟢', '📈'
    elif 'SELL' in action: main_emoji, bias_emoji = '🔴', '📉'
    else: main_emoji, bias_emoji = '⚪️', '➡️'
        
    message = (
        f"*{main_emoji} ANALISIS TEKNIKAL CFTe UNTUK {symbol} {bias_emoji}*\n\n"
        f"*Harga Saat Ini: ${current_price:,.4f}*\n"
        f"----------------------------------------\n\n"
        f"*Analisis Multi-Timeframe:*\n\n"
        f"🕓 *4 Jam (Tren & Kekuatan):* _{analisis.get('h4_trend', 'N/A')}_\n\n"
        f"🕐 *1 Jam (Struktur & Volume):* _{analisis.get('h1_structure', 'N/A')}_\n\n"
        f"⏱️ *15 Menit (Konfirmasi Entri):* _{analisis.get('m15_confirmation', 'N/A')}_\n\n"
        f"*🎯 Konfluensi Sinyal Utama:*\n_{analisis.get('confluence_factors', 'N/A')}_\n\n"
        f"----------------------------------------\n\n"
        f"📌 *SINTESIS & RENCANA TRADING*\n\n"
        f"*{analisis.get('summary', 'N/A')}*\n\n"
    )

    if action != 'NEUTRAL':
        message += (
            f"  - **Aksi:** *{action}*\n"
            f"  - **Area Entry:** *{trade_plan.get('Entry', 'N/A')}*\n"
            f"  - **Take Profit 1:** *{trade_plan.get('TP1', 'N/A')}*\n"
            f"  - **Take Profit 2:** *{trade_plan.get('TP2', 'N/A')}*\n"
            f"  - **Stop Loss:** *{trade_plan.get('SL', 'N/A')}*\n\n"
        )
    
    message += f"*🧠 Alasan Rencana:* _{trade_plan.get('reasoning', 'Tidak ada alasan yang diberikan.')}_\n\n"
    message += "*Disclaimer: Ini adalah analisis otomatis dan bukan nasihat keuangan.*"
    return message

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        if len(message) > 4096: message = message[:4090] + "\n[...]"
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Notifikasi analisis berhasil dikirim ke Telegram.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")

async def main():
    """Fungsi utama untuk menjalankan seluruh alur proses."""
    check_credentials()
    cfg = CONFIG
    
    all_market_data = await fetch_all_data(cfg['symbol'], cfg['timeframes'], cfg['candle_count_for_fetch'], cfg['exchange_id'])
    
    if not all_market_data or any(df is None or df.empty for df in all_market_data.values()):
        failed_tfs = [tf for tf, df in all_market_data.items() if df is None or df.empty]
        await send_telegram_message(f"❌ **Bot Error:** Gagal mengambil data pasar untuk {cfg['symbol']} pada timeframe: {', '.join(failed_tfs)}.")
        return
        
    last_price = all_market_data[cfg['timeframes'][-1]]['close'].iloc[-1]

    all_ta_indicators = {}
    for tf, df in all_market_data.items():
        if df is not None and not df.empty:
            print(f"Menghitung indikator untuk timeframe {tf}...")
            all_ta_indicators[tf] = calculate_ta_indicators(df, cfg['indicators'])

    fibo_df = all_market_data.get(cfg['fibonacci_timeframe'])
    fibo_levels = calculate_fibonacci_retracement(fibo_df, cfg['fibonacci_swing_candles'])
    
    technical_report = format_data_for_gemini(all_market_data, all_ta_indicators, fibo_levels)
    
    # Memanggil fungsi analisis OpenAI yang baru
    analysis_result = await get_openai_analysis(technical_report, cfg['symbol'], cfg['openai_model'], last_price)
    
    if analysis_result is None:
        await send_telegram_message(f"❌ **Bot Error:** Gagal mendapatkan analisis dari OpenAI GPT untuk {cfg['symbol']}.")
        return

    report_message = format_analysis_message(analysis_result, cfg['symbol'], last_price)
    await send_telegram_message(report_message)

if __name__ == "__main__":
    asyncio.run(main())
