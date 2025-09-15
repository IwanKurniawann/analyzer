# -*- coding: utf-8 -*-
"""
Main script for generating a comprehensive market analysis report using the Groq API.
This version is upgraded to be more adaptive and anticipatory by adding ADX
and Volume Analysis, and uses a configuration-based structure.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

import ccxt
import pandas as pd
import pandas_ta as ta
import telegram
from groq import Groq

# --- 1. MAIN CONFIGURATION (ADAPTIVE CODE) ---
# All settings can be changed here. Add new indicators in 'indicators'.
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
    'fibonacci_swing_candles': 60
}

# --- CREDENTIALS & CONSTANTS ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL = 'llama3-70b-8192'

# Type alias for clarity
OhlcvData = Dict[str, Optional[pd.DataFrame]]
IndicatorData = Dict[str, Any]

def check_credentials() -> None:
    """Checks for the presence of necessary credentials."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        sys.exit("Error: Ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.")
    if not GROQ_API_KEY:
        sys.exit("Error: Ensure GROQ_API_KEY is set.")
    print("Credentials successfully verified.")

async def fetch_all_data(symbol: str, timeframes: List[str], limit: int, exchange_id: str) -> OhlcvData:
    """Fetches OHLCV data for all specified timeframes from the selected exchange."""
    all_data: OhlcvData = {}
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
    except (AttributeError, ccxt.ExchangeNotFound):
        print(f"Error: Exchange '{exchange_id}' not found or not supported by CCXT.")
        return {}

    print(f"Initializing data fetch for {symbol} from {exchange_id.title()}...")
    for tf in timeframes:
        try:
            print(f"Fetching last {limit} candles for timeframe {tf}...")
            # Use asyncio.to_thread for blocking ccxt calls
            ohlcv = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            all_data[tf] = df
            print(f"Data for {tf} fetched successfully.")
        except Exception as e:
            print(f"Error fetching data for {tf}: {e}")
            all_data[tf] = None
    return all_data

def calculate_ta_indicators(df: pd.DataFrame, indicator_config: Dict[str, Any]) -> Optional[IndicatorData]:
    """Calculates technical indicators dynamically based on the configuration."""
    if df is None or df.empty:
        return None

    indicators: IndicatorData = {}
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
            ema_values = {f"EMA_{p}": f"{df.iloc[-1].get(f'EMA_{p}', 0):.2f}" for p in ema_lengths}
            df.ta.ema(lengths=ema_lengths, append=True)
            indicators['EMAs'] = ema_values

        # ADX
        if 'adx' in indicator_config:
            adx_length = indicator_config['adx']['length']
            adx_data = df.ta.adx(length=adx_length, append=True)
            if adx_data is not None and not adx_data.empty:
                adx_value = adx_data.iloc[-1].get(f'ADX_{adx_length}', 0)
                indicators['ADX'] = {
                    "ADX": f"{adx_value:.2f}",
                    "Status": "Strong Trend" if adx_value > 25 else "Weak/Ranging Trend"
                }

        # Volume Analysis
        if 'volume_profile' in indicator_config:
            vol_ma_len = indicator_config['volume_profile']['ma_length']
            vol_ma = df['volume'].rolling(window=vol_ma_len).mean()
            last_vol = latest['volume']
            last_vol_ma = vol_ma.iloc[-1]
            indicators['Volume'] = {
                "Last_Volume": f"{last_vol:,.0f}",
                "Volume_MA": f"{last_vol_ma:,.0f}",
                "Status": "Above Average" if last_vol > last_vol_ma else "Below Average"
            }
        return indicators
    except Exception as e:
        print(f"Warning: Failed to calculate TA indicators. Error: {e}")
        return None

def calculate_fibonacci_retracement(df: pd.DataFrame, swing_candles: int) -> Optional[Dict[str, Any]]:
    """Calculates Fibonacci Retracement on the most recent swing."""
    if df is None or len(df) < swing_candles:
        return None

    recent_df = df.tail(swing_candles)
    swing_high = recent_df['high'].max()
    swing_low = recent_df['low'].min()

    if swing_high == swing_low:
        return None

    levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fibo_levels = {f"{level*100:.1f}%": f"{(swing_high - (swing_high - swing_low) * level):.4f}" for level in levels}

    return {
        "swing_high": f"{swing_high:.4f}",
        "swing_low": f"{swing_low:.4f}",
        "levels": fibo_levels
    }

def format_data_for_ai(all_data: OhlcvData, all_ta_indicators: Dict[str, Optional[IndicatorData]], fibo_levels: Optional[Dict[str, Any]]) -> str:
    """Formats the technical data into a structured text report for the AI."""
    report = "Technical market data for analysis:\n\n--- Summary of Technical Indicators (Last Values) ---\n"
    for tf, indicators in all_ta_indicators.items():
        if not indicators: continue
        report += f"**Timeframe: {tf}**\n"
        if 'RSI' in indicators: report += f"- RSI: {indicators['RSI']}\n"
        if 'EMAs' in indicators: report += f"- EMAs: {', '.join([f'{k}: {v}' for k, v in indicators['EMAs'].items()])}\n"
        if 'ADX' in indicators: report += f"- ADX: {indicators['ADX']['ADX']} ({indicators['ADX']['Status']})\n"
        if 'Volume' in indicators: report += f"- Volume: {indicators['Volume']['Status']}\n\n"

    if fibo_levels:
        report += f"--- Fibonacci Retracement from {CONFIG['fibonacci_timeframe']} Swing (Low: ${fibo_levels['swing_low']}, High: ${fibo_levels['swing_high']}) ---\n"
        report += "\n".join([f"Level {level}: ${price}" for level, price in fibo_levels['levels'].items()]) + "\n\n"

    report += "--- Raw Price Data (Last 10 Candles for Context) ---\n"
    for tf, df in all_data.items():
        if df is not None and not df.empty:
            df_subset = df.copy().tail(10)
            df_subset['timestamp'] = df_subset['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            report += f"Data Timeframe: {tf}\n"
            report += df_subset[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_string(index=False) + "\n\n"

    return report

def get_groq_analysis(technical_data_report: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Sends the technical report to Groq and requests a top-down analysis."""
    print("Contacting Groq API for in-depth technical analysis...")
    try:
        client = Groq(api_key=GROQ_API_KEY)

        prompt = (
            "ROLE: You are an elite Certified Financial Technician (CFTe). Your analysis is sharp, methodical, "
            "and always considers trend strength and volume confirmation.\n\n"
            f"ASSET: {symbol}\n\n"
            "CONTEXT: Analyze the following technical data to formulate the highest probability trading scenario.\n\n"
            f"PROVIDED TECHNICAL DATA:\n{technical_data_report}\n\n"
            "TASK: Perform a comprehensive top-down analysis. It is crucial to integrate ADX and Volume data into your analysis for each timeframe.\n"
            "1. **4-Hour Analysis (Macro Trend & Strength):** Determine the main trend based on EMAs. Use ADX to gauge if this trend is strong (ADX > 25) or weakening/ranging. Use volume for confirmation.\n"
            "2. **1-Hour Analysis (Structure & Key Areas):** Identify the market structure (impulsive/corrective). Map key demand/supply areas using Fibonacci levels. Is the current pullback supported by declining volume (indicating a healthy correction)?\n"
            "3. **15-Minute Analysis (Entry Signal & Confirmation):** Describe the confirmation signal you would wait for on the 15M as the price enters the 1H key area. Look for RSI divergence, a spike in volume on reversal, or a valid candle pattern.\n"
            "4. **Synthesis & Confluence:** State at least 3 technical factors that converge (confluence). You must include ADX or Volume as one of the factors.\n"
            "5. **Analysis Summary:** Provide a concise one-sentence summary of the analysis.\n"
            "6. **Trade Plan:** Create a precise and logical trade plan (BUY LIMIT or SELL LIMIT) with Entry, Stop Loss (SL), and two Take Profit (TP1, TP2) levels based on your analysis.\n\n"
            "OUTPUT FORMAT: Provide the output ONLY in a valid JSON object. YOU MUST FILL ALL KEYS. Use the following structure:\n"
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a financial analyst that provides responses in JSON format."},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        response_content = chat_completion.choices[0].message.content
        if response_content:
            analysis = json.loads(response_content)
            print("Analysis from Groq successfully received and processed.")
            return analysis
        return None

    except Exception as e:
        print(f"Error contacting or parsing Groq response: {e}")
        return None


def format_analysis_message(analysis: Dict[str, Any], symbol: str, current_price: float) -> str:
    """Formats the AI's technical analysis for a Telegram notification."""
    analisis = analysis.get('analysis', {})
    trade_plan = analysis.get('trade_plan', {})
    action = trade_plan.get('Action', 'NEUTRAL').upper()

    if 'BUY' in action:
        main_emoji, bias_emoji = '🟢', '📈'
    elif 'SELL' in action:
        main_emoji, bias_emoji = '🔴', '📉'
    else:
        main_emoji, bias_emoji = '⚪️', '➡️'

    return (
        f"*{main_emoji} CFTe TECHNICAL ANALYSIS FOR {symbol} {bias_emoji}*\n\n"
        f"*Current Price: ${current_price:,.4f}*\n"
        f"----------------------------------------\n\n"
        f"*Multi-Timeframe Analysis:*\n\n"
        f"🕓 *4-Hour (Trend & Strength):* _{analisis.get('h4_trend', 'N/A')}_\n\n"
        f"🕐 *1-Hour (Structure & Volume):* _{analisis.get('h1_structure', 'N/A')}_\n\n"
        f"⏱️ *15-Minute (Entry Confirmation):* _{analisis.get('m15_confirmation', 'N/A')}_\n\n"
        f"*🎯 Key Signal Confluence:*\n_{analisis.get('confluence_factors', 'N/A')}_\n\n"
        f"----------------------------------------\n\n"
        f"📌 *SYNTHESIS & TRADE PLAN*\n\n"
        f"*{analisis.get('summary', 'N/A')}*\n\n"
        f"  - **Action:** *{action}*\n"
        f"  - **Entry Area:** *{trade_plan.get('Entry', 'N/A')}*\n"
        f"  - **Take Profit 1:** *{trade_plan.get('TP1', 'N/A')}*\n"
        f"  - **Take Profit 2:** *{trade_plan.get('TP2', 'N/A')}*\n"
        f"  - **Stop Loss:** *{trade_plan.get('SL', 'N/A')}*\n\n"
        f"*Disclaimer: This is an automated analysis and not financial advice.*"
    )

async def send_telegram_message(message: str) -> None:
    """Sends a message to Telegram."""
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        # Handle message length limit by splitting if necessary
        if len(message) > 4096:
            message = message[:4090] + "\n..."
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Analysis notification successfully sent to Telegram.")
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

async def main() -> None:
    """The main function to run the entire process flow."""
    check_credentials()
    cfg = CONFIG

    all_market_data = await fetch_all_data(
        cfg['symbol'], cfg['timeframes'], cfg['candle_count_for_fetch'], cfg['exchange_id']
    )

    if not all_market_data or all_market_data.get(cfg['timeframes'][-1]) is None:
        await send_telegram_message(f"❌ **Bot Error:** Failed to fetch primary market data for {cfg['symbol']}.")
        return

    last_price = all_market_data[cfg['timeframes'][-1]]['close'].iloc[-1]

    all_ta = {tf: calculate_ta_indicators(df, cfg['indicators']) for tf, df in all_market_data.items()}

    fibo_df = all_market_data.get(cfg['fibonacci_timeframe'])
    fibo_levels = calculate_fibonacci_retracement(fibo_df, cfg['fibonacci_swing_candles'])

    technical_report = format_data_for_ai(all_market_data, all_ta, fibo_levels)

    analysis_result = get_groq_analysis(technical_report, cfg['symbol'])

    if not analysis_result:
        await send_telegram_message(f"❌ **Bot Error:** Failed to get analysis from Groq AI for {cfg['symbol']}.")
        return

    report_message = format_analysis_message(analysis_result, cfg['symbol'], last_price)
    await send_telegram_message(report_message)
    print("Process completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
