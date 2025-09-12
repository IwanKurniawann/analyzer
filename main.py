# -*- coding: utf-8 -*-
"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif
menggunakan Google Gemini. Versi ini telah di-upgrade untuk menjadi lebih
adaptif dan antisipatif dengan menambahkan ADX dan Analisis Volume, serta
menggunakan struktur berbasis konfigurasi.
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

# --- 1. KONFIGURASI UTAMA (MEMBUAT KODE ADAPTIF) ---
# Ubah semua pengaturan di sini. Tambahkan indikator baru di 'indicators'.
CONFIG = {
    'symbol': 'SOL/USDT',
    'timeframes': ['4h', '1h', '15m'], # TF 1D dihapus, 15M ditambahkan
    'exchange_id': 'kucoin',  # Ganti ke 'kucoin', 'bybit', dll. jika perlu
    'candle_count_for_fetch': 1000,
    'indicators': {
        'rsi': {'length': 14},
        'ema': {'lengths': [21, 50, 200]},
        'adx': {'length': 14},
        'volume_profile': {'ma_length': 21} # Analisis volume vs moving average-nya
    },
    'fibonacci_timeframe': '1h', # Timeframe acuan untuk Fibonacci
    'fibonacci_swing_candles': 60 # Jumlah candle untuk mencari swing high/low
}

# --- KREDENSIAL ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def check_credentials():
    """Memeriksa kredensial."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        sys.exit("Error: Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID sudah diatur.")
    if not GEMINI_API_KEY:
        sys.exit("Error: Pastikan GEMINI_API_KEY sudah diatur.")

async def fetch_all_data(symbol, timeframes, limit, exchange_id):
    """Mengambil data OHLCV untuk semua timeframe dari exchange yang dipilih."""
    all_data = {}
    try:
        # Menginisialisasi exchange secara dinamis
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
    except (AttributeError, ccxt.ExchangeNotFound):
        print(f"Error: Exchange '{exchange_id}' tidak ditemukan atau tidak didukung oleh CCXT.")
        return None

    print(f"Menginisialisasi pengambilan data untuk {symbol} dari {exchange_id.title()}...")
    for tf in timeframes:
        try:
            print(f"Mengambil {limit} data candle terakhir pada timeframe {tf}...")
            ohlcv = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            all_data[tf] = df
            print(f"Data untuk {tf} berhasil diambil.")
        except Exception as e:
            print(f"Error saat mengambil data untuk {tf}: {e}")
            all_data[tf] = None
    return all_data

def calculate_ta_indicators(df, indicator_config):
    """
    Menghitung indikator teknis secara dinamis berdasarkan konfigurasi.
    Ini adalah jantung dari adaptabilitas skrip.
    """
    if df is None or df.empty: return None
    
    indicators = {}
    latest = df.iloc[-1]

    try:
        # RSI
        if 'rsi' in indicator_config:
            rsi_length = indicator_config['rsi']['length']
            df.ta.rsi(length=rsi_length, append=True)
            indicators['RSI'] = f"{latest.get(f'RSI_{rsi_length}', 0):.2f}"

        # EMAs
        if 'ema' in indicator_config:
            ema_lengths = indicator_config['ema']['lengths']
            ema_values = {}
            for period in ema_lengths:
                df.ta.ema(length=period, append=True)
                ema_values[f"EMA_{period}"] = f"{df.iloc[-1].get(f'EMA_{period}', 0):.2f}"
            indicators['EMAs'] = ema_values

        # ADX (untuk kekuatan tren)
        if 'adx' in indicator_config:
            adx_length = indicator_config['adx']['length']
            adx_data = df.ta.adx(length=adx_length, append=True)
            if adx_data is not None and not adx_data.empty:
                 indicators['ADX'] = {
                    "ADX": f"{adx_data.iloc[-1][f'ADX_{adx_length}']:.2f}",
                    "Status": "Tren Kuat" if adx_data.iloc[-1][f'ADX_{adx_length}'] > 25 else "Tren Lemah / Ranging"
                }

        # Analisis Volume (untuk keyakinan pasar)
        if 'volume_profile' in indicator_config:
            vol_ma_len = indicator_config['volume_profile']['ma_length']
            vol_ma = df['volume'].rolling(window=vol_ma_len).mean()
            last_vol = latest['volume']
            last_vol_ma = vol_ma.iloc[-1]
            status = "Di Atas Rata-rata" if last_vol > last_vol_ma else "Di Bawah Rata-rata"
            indicators['Volume'] = {
                "Last_Volume": f"{last_vol:,.0f}",
                "Volume_MA": f"{last_vol_ma:,.0f}",
                "Status": status
            }

        return indicators
    except Exception as e:
        print(f"Peringatan: Gagal menghitung indikator TA. Error: {e}")
        return None


def calculate_fibonacci_retracement(df, swing_candles):
    """Menghitung Fibonacci Retracement pada swing terakhir."""
    if df is None or len(df) < swing_candles: return None
    
    recent_df = df.tail(swing_candles)
    swing_high = recent_df['high'].max()
    swing_low = recent_df['low'].min()
    
    if swing_high == swing_low: return None

    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fibo_levels = {f"{level*100:.1f}%": f"{(swing_high - (swing_high - swing_low) * level):.2f}" for level in levels}
        
    return {
        "swing_high": f"{swing_high:.2f}",
        "swing_low": f"{swing_low:.2f}",
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

def get_gemini_analysis(technical_data_report, symbol):
    """
    Mengirim laporan teknis ke Gemini dan meminta analisis top-down yang
    mempertimbangkan kekuatan tren (ADX) dan volume.
    """
    try:
        print("Menghubungi Google Gemini untuk analisis teknikal mendalam...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        model = genai.GenerativeModel(
            'gemini-1.5-flash', # Menggunakan model yang lebih baru dan efisien
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        # --- PROMPT YANG TELAH DI-UPGRADE UNTUK TF BARU ---
        prompt = (
            "PERAN: Anda adalah seorang Certified Financial Technician (CFTe) elit. Analisis Anda tajam, metodis, dan selalu mempertimbangkan kekuatan tren serta konfirmasi volume.\n\n"
            f"ASET: {symbol}\n\n"
            "KONTEKS: Analisis data teknis berikut untuk merumuskan satu skenario trading dengan probabilitas tertinggi.\n\n"
            "DATA TEKNIS YANG DISEDIAKAN:\n"
            f"{technical_data_report}\n\n"
            "TUGAS: Lakukan analisis top-down yang komprehensif. **Sangat penting untuk mengintegrasikan data ADX dan Volume ke dalam analisis Anda di setiap timeframe.**\n"
            "1.  **Analisis Timeframe 4 Jam (Tren Makro & Kekuatan):** Tentukan tren utama berdasarkan EMA. Gunakan ADX untuk mengukur apakah tren ini kuat (ADX > 25) atau sedang melemah/ranging. Gunakan volume untuk konfirmasi.\n"
            "2.  **Analisis Timeframe 1 Jam (Struktur & Area Kunci):** Identifikasi struktur pasar (impulsif/korektif). Petakan area demand/supply kunci menggunakan level Fibonacci. Apakah pullback saat ini didukung oleh volume yang menurun (menandakan koreksi sehat)?\n"
            "3.  **Analisis Timeframe 15 Menit (Sinyal Entri & Konfirmasi):** Jelaskan sinyal konfirmasi yang Anda tunggu di 15M saat harga memasuki area kunci 1H. Cari divergensi RSI, peningkatan volume saat pembalikan, atau candle pattern yang valid.\n"
            "4.  **Sintesis & Konfluensi:** Sebutkan minimal 3 faktor teknikal yang bertemu (konfluensi). **Wajib memasukkan ADX atau Volume sebagai salah satu faktor.** Contoh: 'Tren 4H bullish dengan ADX > 30, pullback ke Fibo 61.8% di 1H dengan volume menurun, dan potensi bullish divergence di 15M.'\n"
        	"5.  **Ringkasan Analisis:** Berikan kesimpulan analisis dalam satu kalimat yang padat dan jelas.\n"
        	"6.  **Rencana Trading (Trade Plan):** Buat satu rencana trading (BUY LIMIT atau SELL LIMIT) dengan level Entry, Stop Loss (SL), dan dua Take Profit (TP1, TP2) yang presisi dan logis berdasarkan analisis.\n\n"
            "FORMAT OUTPUT: Berikan output HANYA dalam format JSON yang valid. WAJIB ISI SEMUA KUNCI. Gunakan struktur berikut:\n"
            "{\n"
            "  \"analysis\": {\n"
            "    \"h4_trend\": \"...\",\n"
            "    \"h1_structure\": \"...\",\n"
            "    \"m15_confirmation\": \"...\",\n"
            "    \"confluence_factors\": \"...\",\n"
            "    \"summary\": \"...\"\n"
            "  },\n"
            "  \"trade_plan\": {\n"
            "    \"Action\": \"BUY LIMIT / SELL LIMIT\",\n"
            "    \"Entry\": \"Harga atau rentang harga\",\n"
            "    \"SL\": \"Harga SL\",\n"
            "    \"TP1\": \"Harga TP1\",\n"
            "    \"TP2\": \"Harga TP2\"\n"
            "  }\n"
            "}"
        )
        
        response = model.generate_content(prompt)
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
        analysis = json.loads(cleaned_text)
        print("Analisis dari Gemini berhasil diterima dan diproses.")
        return analysis
            
    except Exception as e:
        print(f"Error saat menghubungi atau mem-parsing respons Gemini: {e}")
        return None

def format_analysis_message(analysis, symbol, current_price):
    """Memformat pesan notifikasi analisis teknikal dari AI."""
    analisis = analysis.get('analysis', {})
    trade_plan = analysis.get('trade_plan', {})
    
    action = trade_plan.get('Action', 'NEUTRAL').upper()
    
    if 'BUY' in action:
        main_emoji, bias_emoji = '🟢', '📈'
    elif 'SELL' in action:
        main_emoji, bias_emoji = '🔴', '📉'
    else:
        main_emoji, bias_emoji = '⚪️', '➡️'
        
    message = (
        f"*{main_emoji} ANALISIS TEKNIKAL CFTe UNTUK {symbol} {bias_emoji}*\n\n"
        f"*Harga Saat Ini: ${current_price:,.2f}*\n"
        f"----------------------------------------\n\n"
        f"*Analisis Multi-Timeframe:*\n\n"
        f"🕓 *4 Jam (Tren & Kekuatan):* _{analisis.get('h4_trend', 'N/A')}_\n\n"
        f"🕐 *1 Jam (Struktur & Volume):* _{analisis.get('h1_structure', 'N/A')}_\n\n"
        f"⏱️ *15 Menit (Konfirmasi Entri):* _{analisis.get('m15_confirmation', 'N/A')}_\n\n"
        f"*🎯 Konfluensi Sinyal Utama:*\n_{analisis.get('confluence_factors', 'N/A')}_\n\n"
        f"----------------------------------------\n\n"
        f"📌 *SINTESIS & RENCANA TRADING*\n\n"
        f"*{analisis.get('summary', 'N/A')}*\n\n"
        f"  - **Aksi:** *{action}*\n"
        f"  - **Area Entry:** *{trade_plan.get('Entry', 'N/A')}*\n"
        f"  - **Take Profit 1:** *{trade_plan.get('TP1', 'N/A')}*\n"
        f"  - **Take Profit 2:** *{trade_plan.get('TP2', 'N/A')}*\n"
        f"  - **Stop Loss:** *{trade_plan.get('SL', 'N/A')}*\n\n"
        f"*Disclaimer: Ini adalah analisis otomatis dan bukan nasihat keuangan.*"
    )
    return message

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        # Handle message length limit
        if len(message) > 4096: message = message[:4090] + "\n..."
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Notifikasi analisis berhasil dikirim ke Telegram.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")

async def main():
    """Fungsi utama untuk menjalankan seluruh alur proses."""
    check_credentials()
    
    cfg = CONFIG # Alias untuk kemudahan
    
    all_market_data = await fetch_all_data(cfg['symbol'], cfg['timeframes'], cfg['candle_count_for_fetch'], cfg['exchange_id'])
    
    if not all_market_data or all_market_data.get(cfg['timeframes'][-1]) is None:
        await send_telegram_message(f"❌ **Bot Error:** Gagal mengambil data pasar utama untuk {cfg['symbol']}.")
        return
        
    last_price = all_market_data[cfg['timeframes'][-1]]['close'].iloc[-1]

    all_ta_indicators = {}
    for tf, df in all_market_data.items():
        print(f"Menghitung indikator untuk timeframe {tf}...")
        all_ta_indicators[tf] = calculate_ta_indicators(df, cfg['indicators'])

    fibo_df = all_market_data.get(cfg['fibonacci_timeframe'])
    fibo_levels = calculate_fibonacci_retracement(fibo_df, cfg['fibonacci_swing_candles'])
    
    technical_report = format_data_for_gemini(all_market_data, all_ta_indicators, fibo_levels)
    
    analysis_result = get_gemini_analysis(technical_report, cfg['symbol'])
    
    if analysis_result is None:
        await send_telegram_message(f"❌ **Bot Error:** Gagal mendapatkan analisis dari Gemini AI untuk {cfg['symbol']}.")
        return

    report_message = format_analysis_message(analysis_result, cfg['symbol'], last_price)
    await send_telegram_message(report_message)

if __name__ == "__main__":
    asyncio.run(main())

