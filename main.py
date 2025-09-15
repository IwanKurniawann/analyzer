# -*- coding: utf-8 -*-
"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif.
Versi ini menggunakan Groq API, yang menyediakan akses super cepat dan gratis
ke model LLM open-source terkemuka seperti Llama 3.
"""

import os
import sys
import ccxt.pro as ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
import telegram
# Groq menggunakan pustaka/format yang sama dengan OpenAI
import openai
import json

# --- 1. KONFIGURASI UTAMA ---
CONFIG = {
    'symbol': 'SOL/USDT',
    'timeframes': ['4h', '1h', '15m'],
    'exchange_id': 'kucoin',
    'candle_count_for_fetch': 1000,
    'indicators': {
        'rsi': {'length': 14},
        'ema': {'lengths': [21, 50, 200]},
        'adx': {'length': 14},
        'volume_profile': {'ma_length': 21}
    },
    'fibonacci_timeframe': '15m',
    'fibonacci_swing_candles': 60,
    # Model yang digunakan di Groq. Anda bisa ganti ke model lain yang didukung Groq.
    'groq_model': 'llama3-8b-8192'
}

# --- KREDENSIAL ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_API_KEY = os.getenv('GROQ_API_KEY') # Kredensial baru untuk Groq

def check_credentials():
    """Memeriksa kredensial."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        sys.exit("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
    if not GROQ_API_KEY:
        sys.exit("Error: Pastikan GROQ_API_KEY sudah diatur.")

async def fetch_all_data(symbol, timeframes, limit, exchange_id):
    """Mengambil data OHLCV secara konkuren."""
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
    """Menghitung indikator teknis."""
    if df is None or df.empty: return None
    indicators = {}
    latest = df.iloc[-1]
    try:
        if 'rsi' in indicator_config:
            rsi_length = indicator_config['rsi']['length']
            df.ta.rsi(length=rsi_length, append=True)
            indicators['RSI'] = f"{df.iloc[-1].get(f'RSI_{rsi_length}', 0):.2f}"
        if 'ema' in indicator_config:
            ema_lengths = indicator_config['ema']['lengths']
            ema_values = {f"EMA_{p}": f"{df.iloc[-1].get(f'EMA_{p}', 0):.2f}" for p in ema_lengths if df.ta.ema(length=p, append=True) is not None}
            indicators['EMAs'] = ema_values
        if 'adx' in indicator_config:
            adx_length = indicator_config['adx']['length']
            adx_data = df.ta.adx(length=adx_length, append=True)
            if adx_data is not None and not adx_data.empty:
                adx_value = adx_data.iloc[-1].get(f'ADX_{adx_length}')
                if adx_value is not None:
                    indicators['ADX'] = {"ADX": f"{adx_value:.2f}", "Status": "Tren Kuat" if adx_value > 25 else "Tren Lemah / Ranging"}
                else:
                    indicators['ADX'] = {"ADX": "N/A", "Status": "Gagal dihitung"}
        if 'volume_profile' in indicator_config:
            vol_ma = df['volume'].rolling(window=indicator_config['volume_profile']['ma_length']).mean()
            status = "Di Atas Rata-rata" if latest['volume'] > vol_ma.iloc[-1] else "Di Bawah Rata-rata"
            indicators['Volume'] = {"Status": status}
        return indicators
    except Exception as e:
        print(f"Peringatan: Gagal menghitung indikator TA. Error: {e}")
        return indicators if indicators else None

def calculate_fibonacci_retracement(df, swing_candles):
    """Menghitung Fibonacci Retracement."""
    if df is None or len(df) < swing_candles: return None
    recent_df = df.tail(swing_candles)
    swing_high, swing_low = recent_df['high'].max(), recent_df['low'].min()
    if swing_high == swing_low: return None
    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fibo_levels = {f"{lvl*100:.1f}%": f"{(swing_high - (swing_high - swing_low) * lvl):.4f}" for lvl in levels}
    return {"swing_high": f"{swing_high:.4f}", "swing_low": f"{swing_low:.4f}", "levels": fibo_levels}

def format_data_for_ai(all_data, all_ta_indicators, fibo_levels):
    """Menyusun laporan data untuk AI."""
    report = "Data teknis pasar untuk dianalisis:\n\n--- Ringkasan Indikator Teknis ---\n"
    for tf, indicators in all_ta_indicators.items():
        if not indicators: continue
        report += f"**Timeframe: {tf}**\n"
        if 'RSI' in indicators: report += f"- RSI: {indicators['RSI']}\n"
        if 'EMAs' in indicators: report += f"- EMAs: {', '.join([f'{k}: {v}' for k, v in indicators['EMAs'].items()])}\n"
        if 'ADX' in indicators: report += f"- ADX: {indicators['ADX']['ADX']} ({indicators['ADX']['Status']})\n"
        if 'Volume' in indicators: report += f"- Volume: {indicators['Volume']['Status']}\n"
        report += "\n"
    if fibo_levels:
        report += f"--- Fibonacci Retracement {CONFIG['fibonacci_timeframe']} (L: ${fibo_levels['swing_low']}, H: ${fibo_levels['swing_high']}) ---\n"
        report += "\n".join([f"Level {level}: ${price}" for level, price in fibo_levels['levels'].items()]) + "\n\n"
    report += "--- Data Harga Mentah (10 Candle Terakhir) ---\n"
    for tf, df in all_data.items():
        if df is not None and not df.empty:
            df_subset = df.copy().tail(10)
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"Data Timeframe: {tf}\n{df_subset[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_string(index=False)}\n\n"
    return report

async def get_groq_analysis(technical_data_report, symbol, model_name, current_price):
    """Mengirim laporan ke Groq dan meminta analisis."""
    try:
        print(f"Menghubungi Groq ({model_name}) untuk analisis...")
        client = openai.AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1", # URL API khusus Groq
            api_key=GROQ_API_KEY
        )
        
        system_prompt = (
            "PERAN: Anda adalah seorang Certified Financial Technician (CFTe) elit yang metodis dan logis dengan pemikiran tajam. Anda hanya membalas dalam format JSON yang valid.\n\n"
            "TUGAS & ATURAN:\n"
            "1. Lakukan analisis multi-timeframe (4H, 1H, 15M) pada data yang diberikan.\n"
            "2. Identifikasi minimal 3 faktor konfluensi.\n"
            "3. Buat satu rencana trading yang logis berdasarkan HARGA SAAT INI.\n"
            "4. 'BUY LIMIT' hanya jika entry di bawah harga saat ini. 'SELL LIMIT' hanya jika entry di atas harga saat ini.\n"
            "5. Jika tidak ada setup, gunakan 'NEUTRAL' dan jelaskan alasannya.\n"
            "6. Berikan alasan singkat untuk rencana trading yang dibuat.\n\n"
            "STRUKTUR JSON OUTPUT:\n"
            '{"analysis": {"h4_trend": "...", "h1_structure": "...", "m15_confirmation": "...", "confluence_factors": "...", "summary": "..."}, "trade_plan": {"Action": "...", "Entry": "...", "SL": "...", "TP1": "...", "TP2": "...", "reasoning": "..."}}'
        )
        user_prompt = (
             f"ASET: {symbol}\nKONTEKS HARGA SAAT INI: ${current_price:,.4f}\n\nDATA TEKNIS:\n{technical_data_report}\n\nLakukan analisis dan hasilkan JSON sesuai aturan."
        )
        
        response = await client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        analysis = json.loads(response.choices[0].message.content)
        print("Analisis dari Groq berhasil diterima.")
        return analysis
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons Groq: {e}")
        return None

def format_analysis_message(analysis, symbol, current_price):
    """Memformat pesan notifikasi."""
    analisis, trade_plan = analysis.get('analysis', {}), analysis.get('trade_plan', {})
    action = trade_plan.get('Action', 'NEUTRAL').upper()
    emoji_map = {'BUY': ('🟢', '📈'), 'SELL': ('🔴', '📉'), 'NEUTRAL': ('⚪️', '➡️')}
    main_emoji, bias_emoji = emoji_map.get(action.split()[0], emoji_map['NEUTRAL'])
    message = (
        f"*{main_emoji} ANALISIS TEKNIKAL CFTe UNTUK {symbol} {bias_emoji}*\n\n"
        f"*Harga Saat Ini: ${current_price:,.4f}*\n"
        f"----------------------------------------\n\n"
        f"*Analisis Multi-Timeframe:*\n\n"
        f"🕓 *4 Jam (Tren & Kekuatan):* _{analisis.get('h4_trend', 'N/A')}_\n"
        f"🕐 *1 Jam (Struktur & Volume):* _{analisis.get('h1_structure', 'N/A')}_\n"
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
    message += f"*🧠 Alasan Rencana:* _{trade_plan.get('reasoning', 'N/A')}_\n\n"
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
    """Fungsi utama."""
    check_credentials()
    cfg = CONFIG
    
    all_market_data = await fetch_all_data(cfg['symbol'], cfg['timeframes'], cfg['candle_count_for_fetch'], cfg['exchange_id'])
    
    if not all_market_data or any(df is None or df.empty for df in all_market_data.values()):
        failed_tfs = [tf for tf, df in all_market_data.items() if df is None or df.empty]
        await send_telegram_message(f"❌ **Bot Error:** Gagal mengambil data pasar untuk {cfg['symbol']} pada timeframe: {', '.join(failed_tfs)}.")
        return
        
    last_price = all_market_data[cfg['timeframes'][-1]]['close'].iloc[-1]
    all_ta_indicators = {tf: calculate_ta_indicators(df, cfg['indicators']) for tf, df in all_market_data.items() if df is not None and not df.empty}
    fibo_levels = calculate_fibonacci_retracement(all_market_data.get(cfg['fibonacci_timeframe']), cfg['fibonacci_swing_candles'])
    technical_report = format_data_for_ai(all_market_data, all_ta_indicators, fibo_levels)
    
    analysis_result = await get_groq_analysis(technical_report, cfg['symbol'], cfg['groq_model'], last_price)
    
    if analysis_result is None:
        await send_telegram_message(f"❌ **Bot Error:** Gagal mendapatkan analisis dari Groq untuk {cfg['symbol']}.")
        return

    report_message = format_analysis_message(analysis_result, cfg['symbol'], last_price)
    await send_telegram_message(report_message)

if __name__ == "__main__":
    asyncio.run(main())
