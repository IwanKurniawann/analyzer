# -*- coding: utf-8 -*-

"""
Skrip utama untuk menghasilkan laporan analisis pasar yang komprehensif
menggunakan Google Gemini. Versi ini telah di-upgrade untuk mengimplementasikan
metodologi analisis Top-Down (Daily -> H4 -> H1) ala Certified Financial
Technician (CFTe), dengan fokus pada EMA, Fibonacci Retracement, dan konfluensi sinyal.
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
TIMEFRAMES = ['1d', '4h', '1h'] # Fokus pada timeframe kunci untuk analisis top-down
CANDLE_COUNT_FOR_FETCH = 200 # Ambil data lebih banyak untuk kalkulasi EMA 200

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

async def fetch_all_data(symbol, timeframes, limit):
    """Mengambil data OHLCV untuk semua timeframe."""
    all_data = {}
    # Gunakan Binance karena lebih umum dan datanya seringkali lebih lengkap
    exchange = ccxt.binance() 
    print(f"Menginisialisasi pengambilan data untuk {symbol}...")
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

def calculate_ta_indicators(df):
    """Menghitung indikator teknis kunci: RSI dan EMA."""
    if df is None or df.empty: return None
    try:
        # Kalkulasi RSI
        df.ta.rsi(length=14, append=True)
        
        # Kalkulasi EMAs
        emas = [21, 50, 200]
        for period in emas:
            df.ta.ema(length=period, append=True)
            
        latest = df.iloc[-1]
        
        # Ekstrak nilai EMA dalam format yang rapi
        ema_values = {f"EMA_{period}": f"{latest.get(f'EMA_{period}', 0):.2f}" for period in emas}

        return {
            'RSI_14': f"{latest.get('RSI_14', 0):.2f}",
            'EMAs': ema_values
        }
    except Exception as e:
        print(f"Peringatan: Gagal menghitung indikator TA. Error: {e}")
        return None

def calculate_fibonacci_retracement(df_h4):
    """Menghitung Fibonacci Retracement pada swing terakhir di H4."""
    if df_h4 is None or len(df_h4) < 50: return None
    
    # Ambil 60 candle terakhir untuk mengidentifikasi swing yang relevan
    recent_df = df_h4.tail(60)
    swing_high = recent_df['high'].max()
    swing_low = recent_df['low'].min()
    
    # Pastikan swing valid
    if swing_high == swing_low: return None

    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fibo_levels = {}
    for level in levels:
        price = swing_high - (swing_high - swing_low) * level
        fibo_levels[f"{level*100:.1f}%"] = f"{price:.2f}"
        
    return {
        "swing_high": f"{swing_high:.2f}",
        "swing_low": f"{swing_low:.2f}",
        "levels": fibo_levels
    }

def format_data_for_gemini(all_data, all_ta_indicators, fibo_levels):
    """Mengubah data teknis menjadi laporan teks yang terstruktur untuk AI."""
    report = "Data teknis pasar untuk dianalisis:\n\n"
    
    # 1. Ringkasan Indikator Multi-Timeframe
    report += "--- Ringkasan Indikator Teknis (Nilai Terakhir) ---\n"
    for tf, indicators in all_ta_indicators.items():
        if indicators:
            emas_str = ", ".join([f"{k}: {v}" for k, v in indicators['EMAs'].items()])
            report += f"TF {tf}: RSI={indicators['RSI_14']}; {emas_str}\n"
    report += "\n"

    # 2. Level Fibonacci Kunci dari H4
    if fibo_levels:
        report += "--- Fibonacci Retracement dari Swing H4 (Swing Low: ${low}, Swing High: ${high}) ---\n".format(
            low=fibo_levels['swing_low'], high=fibo_levels['swing_high']
        )
        for level, price in fibo_levels['levels'].items():
            report += f"Level {level}: ${price}\n"
        report += "\n"
        
    # 3. Data Harga Mentah (sebagai konteks tambahan)
    report += "--- Data Harga Mentah (20 Candle Terakhir) ---\n"
    for tf, df in all_data.items():
        if df is not None and not df.empty:
            df_subset = df.copy().tail(20)
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"Data Timeframe: {tf}\n"
            report += df_subset.to_string(index=False)
            report += "\n\n"
            
    return report

def get_gemini_analysis(technical_data_report):
    """
    Mengirim laporan teknis ke Gemini dan meminta analisis top-down
    sesuai metodologi CFTe dalam format JSON.
    """
    try:
        print("Menghubungi Google Gemini untuk analisis teknikal mendalam...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        model = genai.GenerativeModel(
            'gemini-2.0-flash',
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        prompt = (
            "PERAN: Anda adalah seorang Certified Financial Technician (CFTe) dan analis pasar profesional. Gaya Anda objektif, metodis, dan fokus pada manajemen risiko.\n\n"
            f"ASET: {SYMBOL}\n\n"
            "KONTEKS: Anda diminta untuk menganalisis data teknis berikut dan menghasilkan satu skenario trading paling optimal.\n\n"
            "DATA TEKNIS YANG DISEDIAKAN:\n"
            f"{technical_data_report}\n\n"
            "TUGAS: Lakukan analisis top-down secara ketat berdasarkan data yang ada dan hasilkan rencana trading.\n"
            "1.  **Analisis Timeframe Daily (Tren Jangka Panjang):** Berdasarkan posisi harga relatif terhadap EMA 21, 50, dan 200, tentukan tren utama (Contoh: 'Bullish kuat karena harga di atas semua EMA dan EMA tersusun rapi').\n"
            "2.  **Analisis Timeframe H4 (Struktur & Momentum):** Jelaskan struktur pasar saat ini (impulsif atau korektif). Identifikasi area demand/supply kunci berdasarkan level Fibonacci Retracement yang disediakan, terutama di 'golden pocket' (38.2% - 61.8%).\n"
            "3.  **Analisis Timeframe H1 (Konfirmasi & Eksekusi):** Jelaskan sinyal konfirmasi apa yang akan Anda cari di H1 ketika harga mendekati area kunci dari H4. Perhatikan kondisi RSI (misalnya, 'RSI mendekati oversold').\n"
            "4.  **Sintesis & Konfluensi:** Sebutkan minimal 3 faktor teknikal yang bertemu (konfluensi) yang mendukung rencana trading Anda (Contoh: 'Tren Daily bullish, pullback ke Fibo 50% H4, dan EMA 50 H4 sebagai support dinamis').\n"
            "5.  **Ringkasan Analisis:** Berikan kesimpulan analisis dalam satu kalimat singkat.\n"
            "6.  **Rencana Trading (Trade Plan):** Buat satu rencana trading yang paling probabel (BUY LIMIT atau SELL LIMIT). Tentukan level Entry, Stop Loss (SL), dan dua Take Profit (TP1, TP2) yang logis berdasarkan analisis Fibonacci dan struktur pasar.\n\n"
            "FORMAT OUTPUT: Berikan output HANYA dalam format JSON yang valid. WAJIB ISI SEMUA KUNCI. Gunakan struktur berikut:\n"
            "{\n"
            "  \"analysis\": {\n"
            "    \"daily_trend\": \"...\",\n"
            "    \"h4_structure\": \"...\",\n"
            "    \"h1_confirmation\": \"...\",\n"
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

def format_analysis_message(analysis, current_price):
    """Memformat pesan notifikasi analisis teknikal dari AI."""
    analisis = analysis.get('analysis', {})
    daily_trend = analisis.get('daily_trend', 'N/A')
    h4_structure = analisis.get('h4_structure', 'N/A')
    h1_confirmation = analisis.get('h1_confirmation', 'N/A')
    confluence = analisis.get('confluence_factors', 'N/A')
    summary = analisis.get('summary', 'N/A')
    
    trade_plan = analysis.get('trade_plan', {})
    action = trade_plan.get('Action', 'NEUTRAL').upper()
    entry = trade_plan.get('Entry', 'N/A')
    tp1 = trade_plan.get('TP1', 'N/A')
    tp2 = trade_plan.get('TP2', 'N/A')
    sl = trade_plan.get('SL', 'N/A')
    
    if 'BUY' in action:
        main_emoji = '🟢'
        bias_emoji = '📈'
    elif 'SELL' in action:
        main_emoji = '🔴'
        bias_emoji = '📉'
    else:
        main_emoji = '⚪️'
        bias_emoji = '횡'
        
    message = (
        f"*{main_emoji} ANALISIS TEKNIKAL CFTe UNTUK {SYMBOL} {bias_emoji}*\n\n"
        f"*Harga Saat Ini: ${current_price:,.2f}*\n"
        f"----------------------------------------\n\n"
        f"*Analisis Multi-Timeframe:*\n\n"
        f"🗓️ *Daily (Tren):* _{daily_trend}_\n\n"
        f"🕓 *H4 (Struktur):* _{h4_structure}_\n\n"
        f"🕐 *H1 (Konfirmasi):* _{h1_confirmation}_\n\n"
        f"*🎯 Konfluensi Sinyal:*\n_{confluence}_\n\n"
        f"----------------------------------------\n\n"
        f"📌 *SINTESIS & RENCANA TRADING*\n\n"
        f"*{summary}*\n\n"
        f"  - **Aksi:** *{action}*\n"
        f"  - **Area Entry:** *{entry}*\n"
        f"  - **Take Profit 1:** *{tp1}*\n"
        f"  - **Take Profit 2:** *{tp2}*\n"
        f"  - **Stop Loss:** *{sl}*\n\n"
        f"*Disclaimer: Ini adalah analisis otomatis dan bukan nasihat keuangan.*"
    )
    return message

async def send_telegram_message(message):
    """Mengirim pesan ke Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        if len(message) > 4096: message = message[:4090] + "\n..."
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Notifikasi analisis berhasil dikirim ke Telegram.")
    except Exception as e:
        print(f"Error saat mengirim pesan ke Telegram: {e}")

async def main():
    check_credentials()
    
    all_market_data = await fetch_all_data(SYMBOL, TIMEFRAMES, CANDLE_COUNT_FOR_FETCH)
    
    if all_market_data.get('1h') is None or all_market_data['1h'].empty:
        await send_telegram_message(f"❌ **Bot Error:** Gagal mengambil data pasar utama untuk {SYMBOL}.")
        return
    last_price = all_market_data['1h']['close'].iloc[-1]

    # Hitung Indikator untuk setiap timeframe
    all_ta_indicators = {}
    for tf, df in all_market_data.items():
        all_ta_indicators[tf] = calculate_ta_indicators(df)

    # Hitung Fibonacci hanya pada timeframe H4
    fibo_levels = calculate_fibonacci_retracement(all_market_data.get('4h'))
    
    # Format semua data teknis menjadi satu laporan
    technical_report = format_data_for_gemini(all_market_data, all_ta_indicators, fibo_levels)
    
    # Kirim ke Gemini untuk dianalisis
    analysis_result = get_gemini_analysis(technical_report)
    
    if analysis_result is None:
        await send_telegram_message(f"❌ **Bot Error:** Gagal mendapatkan analisis dari Gemini AI untuk {SYMBOL}.")
        return

    report_message = format_analysis_message(analysis_result, last_price)
    await send_telegram_message(report_message)

if __name__ == "__main__":
    asyncio.run(main())

