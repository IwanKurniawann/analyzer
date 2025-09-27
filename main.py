import os
import json
import time
import logging
import pandas as pd
import numpy as np
import pandas_ta as ta
import ccxt
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Tuple, Optional
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_log.txt'),
        logging.StreamHandler()
    ]
)

class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        
    def send_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """Send message to Telegram with thread safety"""
        if not self.bot_token or not self.chat_id:
            self.logger.warning("Telegram credentials not configured")
            return False
            
        url = f"{self.base_url}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True
        }
        
        try:
            with self._lock:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                time.sleep(1.2)  # Rate limiting
                
            self.logger.info("Telegram message sent successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def format_trading_signal(self, signal: Dict, symbol: str) -> str:
        """Format trading signal for Telegram per coin with hybrid analysis"""
        emoji_map = {'buy': 'ðŸŸ¢', 'sell': 'ðŸ”´', 'hold': 'âšª'}
        action = signal.get('action', 'hold')
        emoji = emoji_map.get(action, 'âšª')
        coin_name = symbol.replace('/USDT', '').replace('/BTC', '').replace('/ETH', '')
        
        message = f"""
ðŸ¤– *{coin_name} Analysis Report* (KuCoin - Hybrid SMA+EMA)

{emoji} *Action*: {action.upper()}
ðŸ“Š *Confidence*: {signal.get('confidence', 0):.2%}
ðŸ’° *Current Price*: ${signal.get('analysis', {}).get('current_price', 0):.6f}
ðŸ“ˆ *24h Change*: {signal.get('analysis', {}).get('price_change_24h', 0):.2f}%
"""

        if action in ['buy', 'sell']:
            message += f"""
ðŸŽ¯ *Entry Price*: ${signal.get('entry_price', 0):.6f}
ðŸ›‘ *Stop Loss*: ${signal.get('stop_loss', 0):.6f}
ðŸŽ *Take Profit*: ${signal.get('take_profit', 0):.6f}
ðŸ“ˆ *R:R Ratio*: {signal.get('risk_reward_ratio', 0):.2f}
"""

        # Enhanced technical indicators with hybrid analysis
        analysis = signal.get('analysis', {})
        indicators = analysis.get('indicators', {})
        
        message += f"""
ðŸ“Š *Technical Analysis* (Hybrid SMA+EMA):
â€¢ RSI: {indicators.get('rsi', 0):.1f} ({indicators.get('rsi_signal', 'N/A')})
â€¢ MACD: {indicators.get('macd_signal_trend', 'Neutral').title()}
â€¢ BB Position: {indicators.get('bb_position', 'N/A')}
â€¢ Volume Trend: {indicators.get('volume_trend', 0):.1f}%
â€¢ ATR: {indicators.get('atr', 0):.6f}

ðŸ” *Hybrid SMA+EMA Analysis*:
â€¢ Trend Alignment: {indicators.get('trend_alignment', 'N/A').replace('_', ' ').title()}
â€¢ Entry Readiness: {indicators.get('entry_readiness', 'N/A').replace('_', ' ').title()}
â€¢ Structure Strength: {indicators.get('structure_strength', 'N/A').title()}
â€¢ Hybrid Score: {indicators.get('hybrid_confidence', 0):.2f}

ðŸŽ¯ *SMA Levels* (Structure - 70% weight):
â€¢ SMA 20: ${indicators.get('sma_20', 0):.6f}
â€¢ SMA 50: ${indicators.get('sma_50', 0):.6f}
â€¢ Price vs SMA50: {indicators.get('price_vs_sma50', 0):.2f}%

âš¡ *EMA Levels* (Timing - 30% weight):
â€¢ EMA 12: ${indicators.get('ema_12', 0):.6f}
â€¢ EMA 21: ${indicators.get('ema_21', 0):.6f}
â€¢ Price vs EMA12: {indicators.get('price_vs_ema12', 0):.2f}%

ðŸ” *Smart Money Concepts*:
â€¢ Territory: {analysis.get('discount_premium', {}).get('territory', 'N/A').replace('_', ' ').title()}
â€¢ Range Position: {analysis.get('discount_premium', {}).get('percentage_in_range', 0):.1f}%
â€¢ Market Structure: {analysis.get('structure', {}).get('trend', 'N/A').title()}
â€¢ Order Blocks: {len(analysis.get('order_blocks', []))}
â€¢ Manipulation: {'âœ…' if analysis.get('manipulation', {}).get('is_manipulation_phase') else 'âŒ'}

ðŸ“Š *Market Data*:
â€¢ Volume (24h): ${analysis.get('volume_24h', 0):,.0f}
â€¢ Market Rank: #{analysis.get('market_rank', 'N/A')}

ðŸ• *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}
ðŸ’± *Exchange*: KuCoin
ðŸ”§ *Engine*: Hybrid SMA+EMA v2.1
"""
        return message
    
    def send_analysis_report(self, signal: Dict, symbol: str) -> bool:
        """Send formatted analysis report for specific coin"""
        try:
            message = self.format_trading_signal(signal, symbol)
            return self.send_message(message)
        except Exception as e:
            self.logger.error(f"Error formatting Telegram message for {symbol}: {e}")
            return False

    def send_summary_report(self, results: Dict) -> bool:
        """Send summary report of all analyzed coins with hybrid insights"""
        try:
            total_coins = len(results)
            buy_signals = len([r for r in results.values() if r.get('action') == 'buy'])
            sell_signals = len([r for r in results.values() if r.get('action') == 'sell'])
            hold_signals = len([r for r in results.values() if r.get('action') == 'hold'])
            
            # Get top signals with hybrid scoring
            trading_signals = [(symbol, result) for symbol, result in results.items() 
                             if result.get('action') in ['buy', 'sell']]
            trading_signals.sort(key=lambda x: x[1].get('confidence', 0), reverse=True)
            
            # Calculate hybrid statistics
            hybrid_scores = [r.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0) 
                           for r in results.values() if not r.get('error')]
            avg_hybrid_score = np.mean(hybrid_scores) if hybrid_scores else 0
            
            message = f"""
ðŸ“Š *Multi-Coin Analysis Summary* (Hybrid SMA+EMA v2.1)

ðŸ” *Analysis Results*:
â€¢ Total Coins Analyzed: {total_coins}
â€¢ ðŸŸ¢ Buy Signals: {buy_signals}
â€¢ ðŸ”´ Sell Signals: {sell_signals}  
â€¢ âšª Hold Signals: {hold_signals}

ðŸŽ¯ *Hybrid System Performance*:
â€¢ Average Hybrid Score: {avg_hybrid_score:.2f}
â€¢ SMA Weight: 70% (Structure & Stability)
â€¢ EMA Weight: 30% (Timing & Responsiveness)
â€¢ Quality Threshold: 75% confidence

ðŸ† *Top Trading Opportunities*:
"""
            
            # Show top 8 trading signals
            for i, (symbol, result) in enumerate(trading_signals[:8], 1):
                coin = symbol.replace('/USDT', '')
                action = result.get('action', 'hold').upper()
                confidence = result.get('confidence', 0)
                price = result.get('analysis', {}).get('current_price', 0)
                hybrid_score = result.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0)
                
                emoji = 'ðŸŸ¢' if action == 'BUY' else 'ðŸ”´' if action == 'SELL' else 'âšª'
                message += f"\n{i}. {emoji} *{coin}*: {action} ({confidence:.1%}) - ${price:.6f}"
                message += f"\n   ðŸ’¡ Hybrid Score: {hybrid_score:.2f} | Structure+Timing Aligned"
            
            if not trading_signals:
                message += "\nâ€¢ No high-confidence signals found at this time"
                message += "\nâ€¢ All coins below 75% confidence threshold"
            
            message += f"""

ðŸ”§ *System Information*:
â€¢ Engine: Hybrid SMA+EMA Multi-Coin Analyzer v2.1
â€¢ Processing: 8-thread parallel analysis
â€¢ Quality Filter: High-confidence signals only
â€¢ Risk Management: ATR-based dynamic stops

ðŸ• *Analysis Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}
ðŸ’± *Exchange*: KuCoin via CCXT
ðŸ¤– *Strategy*: Smart Money Concepts + Hybrid Technical Analysis
"""
            
            return self.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Error sending summary report: {e}")
            return False

class MultiCoinHybridAnalyzer:
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        self.api_key = api_key or os.getenv('KUCOIN_API_KEY')
        self.api_secret = api_secret or os.getenv('KUCOIN_API_SECRET')
        self.api_passphrase = os.getenv('KUCOIN_API_PASSPHRASE')
        self.testnet = testnet
        self.logger = logging.getLogger(__name__)
        
        # Initialize KuCoin exchange
        self.exchange = self._initialize_exchange()
        
        # Load configuration
        self.config = self.load_config()
        
        # Initialize Telegram notifier
        self.telegram = TelegramNotifier()
        
        # Get tradeable symbols
        self.symbols = self.get_tradeable_symbols()
        
        self.logger.info("Multi-Coin Hybrid Analyzer v2.1 initialized successfully")
        
    def _initialize_exchange(self):
        """Initialize KuCoin exchange via CCXT"""
        try:
            exchange = ccxt.kucoin({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.api_passphrase,
                'sandbox': self.testnet,
                'rateLimit': 100,
                'enableRateLimit': True,
                'options': {'fetchCurrencies': False}
            })
            
            self.logger.info("KuCoin exchange initialized successfully")
            return exchange
            
        except Exception as e:
            self.logger.error(f"Failed to initialize KuCoin exchange: {e}")
            return ccxt.kucoin({
                'sandbox': self.testnet,
                'rateLimit': 100,
                'enableRateLimit': True,
            })
    
    def load_config(self) -> Dict:
        """Load configuration from config.json"""
        try:
            if os.path.exists('config.json'):
                with open('config.json', 'r') as f:
                    return json.load(f)
            else:
                self.logger.warning("config.json not found, using default settings")
                return self.get_default_config()
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict:
        """Return default configuration for multi-coin hybrid analysis"""
        return {
            "trading_config": {
                "coins_to_analyze": [
                    "SOL/USDT", "ETH/USDT", "BTC/USDT", "ADA/USDT", "DOT/USDT",
                    "PENGU/USDT", "AVAX/USDT", "ATOM/USDT", "LINK/USDT", "UNI/USDT",
                    "AAVE/USDT", "SAND/USDT", "MANA/USDT", "APT/USDT", "ALGO/USDT",
                    "XRP/USDT", "BNB/USDT", "LTC/USDT", "TRX/USDT", "VET/USDT",
                    "NEAR/USDT", "ICP/USDT", "FIL/USDT", "ETC/USDT", "XLM/USDT"
                ],
                "min_volume_24h": 1000000,
                "max_coins_per_run": 25,
                "parallel_analysis": True,
                "max_workers": 8,
                "exchange": "kucoin",
                "risk_management": {
                    "max_risk_per_trade": 0.02,
                    "stop_loss_atr_multiplier": 1.5,
                    "take_profit_atr_multiplier": 3.0
                },
                "strategy_parameters": {
                    "discount_threshold": 0.5,
                    "order_block_confidence_threshold": 0.70,
                    "manipulation_detection_period": 20,
                    "order_block_proximity_threshold": 0.02,
                    "rsi_oversold": 30,
                    "rsi_overbought": 70,
                    "min_confidence_for_signal": 0.75,
                    "hybrid_approach_enabled": True
                },
                "technical_indicators": {
                    "approach": "hybrid",
                    "sma_weight": 0.70,
                    "ema_weight": 0.30,
                    "sma_periods": [20, 50, 100, 200],
                    "ema_periods": [9, 12, 21, 50]
                },
                "notification": {
                    "enabled": True,
                    "send_individual_signals": True,
                    "send_summary_report": True,
                    "only_high_confidence": True,
                    "max_notifications_per_run": 12
                }
            }
        }
    
    def get_tradeable_symbols(self) -> List[str]:
        """Get list of tradeable symbols from config"""
        try:
            config_coins = self.config.get('trading_config', {}).get('coins_to_analyze', [])
            
            if config_coins:
                self.logger.info(f"Using configured coins: {len(config_coins)} symbols")
                return config_coins
            
            # Fallback: Get top volume coins from exchange
            markets = self.exchange.fetch_tickers()
            usdt_pairs = [(symbol, ticker) for symbol, ticker in markets.items() 
                         if '/USDT' in symbol and ticker.get('quoteVolume', 0) > 1000000]
            
            usdt_pairs.sort(key=lambda x: x[1].get('quoteVolume', 0), reverse=True)
            top_symbols = [pair[0] for pair in usdt_pairs[:25]]
            
            self.logger.info(f"Auto-selected top {len(top_symbols)} volume pairs")
            return top_symbols
            
        except Exception as e:
            self.logger.error(f"Error getting tradeable symbols: {e}")
            return [
                "SOL/USDT", "ETH/USDT", "BTC/USDT", "ADA/USDT", "DOT/USDT",
                "MATIC/USDT", "AVAX/USDT", "ATOM/USDT", "LINK/USDT", "UNI/USDT"
            ]
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '4h', limit: int = 200) -> pd.DataFrame:
        """Fetch OHLCV data from KuCoin for specific symbol"""
        try:
            self.logger.debug(f"Fetching {symbol} data ({timeframe})")
            
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )
            
            if not ohlcv:
                self.logger.warning(f"No data received for {symbol}")
                return pd.DataFrame()
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col])
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_market_data(self, symbol: str) -> Dict:
        """Get additional market data for symbol"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'volume_24h': ticker.get('quoteVolume', 0),
                'price_change_24h': ticker.get('percentage', 0),
                'high_24h': ticker.get('high', 0),
                'low_24h': ticker.get('low', 0),
                'market_rank': None
            }
        except Exception as e:
            self.logger.error(f"Error fetching market data for {symbol}: {e}")
            return {
                'volume_24h': 0, 'price_change_24h': 0,
                'high_24h': 0, 'low_24h': 0, 'market_rank': None
            }
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate technical indicators using HYBRID SMA+EMA approach"""
        try:
            if df.empty or len(df) < 50:
                return {}
            
            # HYBRID APPROACH: SMA for structure, EMA for timing
            
            # SMA for Structure & Stability (70% weight)
            df.ta.sma(length=20, append=True)
            df.ta.sma(length=50, append=True)
            df.ta.sma(length=100, append=True)
            df.ta.sma(length=200, append=True)
            
            # EMA for Timing & Responsiveness (30% weight)
            df.ta.ema(length=9, append=True)
            df.ta.ema(length=12, append=True)
            df.ta.ema(length=21, append=True)
            df.ta.ema(length=50, append=True)
            
            # Other indicators
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.atr(length=14, append=True)
            df.ta.ad(append=True)
            
            latest = df.iloc[-1]
            
            indicators = {
                # HYBRID SMA/EMA SYSTEM
                'sma_20': latest.get('SMA_20', np.nan),
                'sma_50': latest.get('SMA_50', np.nan),
                'sma_100': latest.get('SMA_100', np.nan),
                'sma_200': latest.get('SMA_200', np.nan),
                'ema_9': latest.get('EMA_9', np.nan),
                'ema_12': latest.get('EMA_12', np.nan),
                'ema_21': latest.get('EMA_21', np.nan),
                'ema_50': latest.get('EMA_50', np.nan),
                
                # MOMENTUM & TREND
                'rsi': latest.get('RSI_14', np.nan),
                'rsi_signal': self._get_rsi_signal(latest.get('RSI_14', 50)),
                'macd': latest.get('MACD_12_26_9', np.nan),
                'macd_signal': latest.get('MACDs_12_26_9', np.nan),
                'macd_signal_trend': self._get_macd_signal(latest),
                
                # VOLATILITY
                'bb_upper': latest.get('BBU_20_2.0', np.nan),
                'bb_middle': latest.get('BBM_20_2.0', np.nan),
                'bb_lower': latest.get('BBL_20_2.0', np.nan),
                'bb_position': self._get_bb_position(latest),
                'atr': latest.get('ATR_14', np.nan),
                
                # VOLUME
                'volume_trend': self._get_volume_trend(df),
                'ad_line': latest.get('AD', np.nan),
                
                # HYBRID ANALYSIS
                'trend_alignment': self._get_hybrid_trend_alignment(latest),
                'entry_readiness': self._get_ema_entry_readiness(latest),
                'structure_strength': self._get_sma_structure_strength(latest),
                'hybrid_confidence': self._calculate_hybrid_confidence(latest, df)
            }
            
            # Price relationships
            current_price = latest['close']
            
            if not np.isnan(indicators['sma_20']):
                indicators['price_vs_sma20'] = (current_price / indicators['sma_20'] - 1) * 100
            if not np.isnan(indicators['sma_50']):
                indicators['price_vs_sma50'] = (current_price / indicators['sma_50'] - 1) * 100
            if not np.isnan(indicators['ema_12']):
                indicators['price_vs_ema12'] = (current_price / indicators['ema_12'] - 1) * 100
            if not np.isnan(indicators['ema_21']):
                indicators['price_vs_ema21'] = (current_price / indicators['ema_21'] - 1) * 100
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Error calculating hybrid technical indicators: {e}")
            return {}
    
    def _get_rsi_signal(self, rsi: float) -> str:
        """Determine RSI signal"""
        if pd.isna(rsi):
            return 'neutral'
        if rsi < 30:
            return 'oversold'
        elif rsi > 70:
            return 'overbought'
        else:
            return 'neutral'
    
    def _get_macd_signal(self, latest: pd.Series) -> str:
        """Determine MACD signal"""
        try:
            macd = latest.get('MACD_12_26_9', np.nan)
            macd_signal = latest.get('MACDs_12_26_9', np.nan)
            
            if pd.isna(macd) or pd.isna(macd_signal):
                return 'neutral'
                
            return 'bullish' if macd > macd_signal else 'bearish'
        except:
            return 'neutral'
    
    def _get_bb_position(self, latest: pd.Series) -> str:
        """Determine Bollinger Bands position"""
        try:
            price = latest['close']
            bb_upper = latest.get('BBU_20_2.0', np.nan)
            bb_lower = latest.get('BBL_20_2.0', np.nan)
            bb_middle = latest.get('BBM_20_2.0', np.nan)
            
            if pd.isna(bb_upper) or pd.isna(bb_lower) or pd.isna(bb_middle):
                return 'N/A'
            
            if price >= bb_upper:
                return 'Above Upper'
            elif price <= bb_lower:
                return 'Below Lower'
            elif price > bb_middle:
                return 'Upper Half'
            else:
                return 'Lower Half'
        except:
            return 'N/A'
    
    def _get_volume_trend(self, df: pd.DataFrame) -> float:
        """Calculate volume trend"""
        try:
            if len(df) < 10:
                return 0
            
            volume_sma_short = df['volume'].tail(5).mean()
            volume_sma_long = df['volume'].tail(20).mean()
            
            return (volume_sma_short / volume_sma_long - 1) * 100
        except:
            return 0
    
    def _get_hybrid_trend_alignment(self, latest: pd.Series) -> str:
        """Get hybrid trend alignment using SMA for structure"""
        try:
            sma_20 = latest.get('SMA_20', np.nan)
            sma_50 = latest.get('SMA_50', np.nan)
            sma_100 = latest.get('SMA_100', np.nan)
            sma_200 = latest.get('SMA_200', np.nan)
            current_price = latest['close']
            
            if any(np.isnan([sma_20, sma_50, sma_100, sma_200])):
                return 'neutral'
            
            alignment_score = 0
            
            # Price above SMAs
            if current_price > sma_20: alignment_score += 1
            if current_price > sma_50: alignment_score += 1
            if current_price > sma_100: alignment_score += 1  
            if current_price > sma_200: alignment_score += 1
            
            # SMA ordering
            if sma_20 > sma_50: alignment_score += 1
            if sma_50 > sma_100: alignment_score += 1
            if sma_100 > sma_200: alignment_score += 1
            
            if alignment_score >= 6:
                return 'strong_bullish'
            elif alignment_score >= 4:
                return 'bullish'
            elif alignment_score <= 1:
                return 'strong_bearish'
            elif alignment_score <= 3:
                return 'bearish'
            else:
                return 'neutral'
                
        except Exception:
            return 'neutral'
    
    def _get_ema_entry_readiness(self, latest: pd.Series) -> str:
        """Get EMA-based entry readiness"""
        try:
            ema_9 = latest.get('EMA_9', np.nan)
            ema_12 = latest.get('EMA_12', np.nan)
            ema_21 = latest.get('EMA_21', np.nan)
            current_price = latest['close']
            
            if any(np.isnan([ema_9, ema_12, ema_21])):
                return 'not_ready'
            
            entry_score = 0
            
            if current_price > ema_9: entry_score += 1
            if current_price > ema_12: entry_score += 1
            if current_price > ema_21: entry_score += 1
            if ema_9 > ema_12: entry_score += 1
            if ema_12 > ema_21: entry_score += 1
            
            if entry_score >= 5:
                return 'buy_ready'
            elif entry_score == 0:
                return 'sell_ready'
            elif entry_score <= 2:
                return 'bearish_setup'
            else:
                return 'bullish_setup'
                
        except Exception:
            return 'not_ready'
    
    def _get_sma_structure_strength(self, latest: pd.Series) -> str:
        """Get SMA-based structure strength"""
        try:
            sma_20 = latest.get('SMA_20', np.nan)
            sma_50 = latest.get('SMA_50', np.nan)
            sma_100 = latest.get('SMA_100', np.nan)
            
            if any(np.isnan([sma_20, sma_50, sma_100])):
                return 'weak'
            
            strength_score = 0
            
            # SMA slopes (simplified)
            sma_20_slope = (sma_20 - sma_20 * 0.999) / (sma_20 * 0.999)
            sma_50_slope = (sma_50 - sma_50 * 0.999) / (sma_50 * 0.999)
            
            if sma_20_slope > 0.001: strength_score += 1
            if sma_50_slope > 0.001: strength_score += 1
            
            sma_separation = abs(sma_20 - sma_50) / sma_50
            if sma_separation > 0.02: strength_score += 1
            
            if strength_score >= 3:
                return 'very_strong'
            elif strength_score == 2:
                return 'strong'
            elif strength_score == 1:
                return 'moderate'
            else:
                return 'weak'
                
        except Exception:
            return 'weak'
    
    def _calculate_hybrid_confidence(self, latest: pd.Series, df: pd.DataFrame) -> float:
        """Calculate confidence using hybrid SMA+EMA approach"""
        try:
            base_confidence = 0.5
            
            # SMA structure confidence (70% weight)
            structure_strength = self._get_sma_structure_strength(latest)
            structure_bonus = {
                'very_strong': 0.25, 'strong': 0.20,
                'moderate': 0.10, 'weak': 0.0
            }.get(structure_strength, 0.0)
            
            # EMA timing confidence (30% weight)  
            entry_readiness = self._get_ema_entry_readiness(latest)
            timing_bonus = {
                'buy_ready': 0.15, 'sell_ready': 0.15,
                'bullish_setup': 0.08, 'bearish_setup': 0.08,
                'not_ready': 0.0
            }.get(entry_readiness, 0.0)
            
            # Trend alignment bonus
            trend_alignment = self._get_hybrid_trend_alignment(latest)
            alignment_bonus = {
                'strong_bullish': 0.10, 'bullish': 0.05,
                'strong_bearish': 0.10, 'bearish': 0.05,
                'neutral': 0.0
            }.get(trend_alignment, 0.0)
            
            # Volume confirmation
            volume_trend = self._get_volume_trend(df)
            volume_bonus = 0.05 if abs(volume_trend) > 10 else 0.0
            
            total_confidence = base_confidence + structure_bonus + timing_bonus + alignment_bonus + volume_bonus
            return min(total_confidence, 1.0)
            
        except Exception:
            return 0.5
    
    def detect_market_structure(self, df: pd.DataFrame) -> Dict:
        """Detect market structure using hybrid approach"""
        if len(df) < 20:
            return {'trend': 'sideways', 'swing_highs': [], 'swing_lows': []}
            
        try:
            swing_high_indices = []
            swing_low_indices = []
            
            for i in range(5, len(df) - 5):
                if df.iloc[i]['high'] == df.iloc[i-5:i+6]['high'].max():
                    swing_high_indices.append(i)
                    
                if df.iloc[i]['low'] == df.iloc[i-5:i+6]['low'].min():
                    swing_low_indices.append(i)
            
            # Determine trend
            trend = 'sideways'
            if len(swing_high_indices) >= 2 and len(swing_low_indices) >= 2:
                recent_highs = [df.iloc[i]['high'] for i in swing_high_indices[-2:]]
                recent_lows = [df.iloc[i]['low'] for i in swing_low_indices[-2:]]
                
                if recent_highs[-1] > recent_highs[-2] and recent_lows[-1] > recent_lows[-2]:
                    trend = 'uptrend'
                elif recent_highs[-1] < recent_highs[-2] and recent_lows[-1] < recent_lows[-2]:
                    trend = 'downtrend'
                    
            return {
                'trend': trend,
                'swing_highs': [(df.index[i], df.iloc[i]['high']) for i in swing_high_indices[-5:]],
                'swing_lows': [(df.index[i], df.iloc[i]['low']) for i in swing_low_indices[-5:]]
            }
            
        except Exception as e:
            self.logger.error(f"Error in market structure detection: {e}")
            return {'trend': 'sideways', 'swing_highs': [], 'swing_lows': []}
    
    def detect_order_blocks(self, df: pd.DataFrame, structure: Dict, indicators: Dict) -> List[Dict]:
        """Enhanced order block detection with hybrid confirmation"""
        order_blocks = []
        
        if structure['trend'] == 'sideways':
            return order_blocks
            
        try:
            recent_df = df.tail(30).copy()
            atr = indicators.get('atr', recent_df['high'].subtract(recent_df['low']).mean())
            
            for i in range(3, len(recent_df) - 1):
                current = recent_df.iloc[i]
                
                # Enhanced filtering with hybrid confirmation
                volume_threshold = recent_df['volume'].mean() * 1.4  # Stricter
                body_size = abs(current['close'] - current['open'])
                candle_range = current['high'] - current['low']
                
                if current['volume'] < volume_threshold or body_size < candle_range * 0.5:
                    continue
                
                # Bullish order blocks with hybrid confirmation
                if (structure['trend'] in ['uptrend'] and
                    current['close'] > current['open'] and
                    body_size > atr * 0.7):  # Stricter requirement
                    
                    future_data = recent_df.iloc[i+1:]
                    if not future_data.empty and future_data['high'].max() > current['high'] * 1.015:  # 1.5% move
                        order_block = {
                            'type': 'bullish',
                            'timestamp': current.name,
                            'high': current['high'],
                            'low': current['low'],
                            'confidence': self.calculate_ob_confidence_hybrid(current, recent_df, 'bullish', indicators),
                            'volume': current['volume']
                        }
                        order_blocks.append(order_block)
                
                # Bearish order blocks with hybrid confirmation
                elif (structure['trend'] in ['downtrend'] and
                      current['close'] < current['open'] and
                      body_size > atr * 0.7):
                    
                    future_data = recent_df.iloc[i+1:]
                    if not future_data.empty and future_data['low'].min() < current['low'] * 0.985:  # 1.5% move
                        order_block = {
                            'type': 'bearish',
                            'timestamp': current.name,
                            'high': current['high'],
                            'low': current['low'],
                            'confidence': self.calculate_ob_confidence_hybrid(current, recent_df, 'bearish', indicators),
                            'volume': current['volume']
                        }
                        order_blocks.append(order_block)
            
            # Sort by confidence and return top 3
            order_blocks.sort(key=lambda x: x['confidence'], reverse=True)
            return order_blocks[:3]
            
        except Exception as e:
            self.logger.error(f"Error detecting order blocks: {e}")
            return []
    
    def calculate_ob_confidence_hybrid(self, candle: pd.Series, df: pd.DataFrame, ob_type: str, indicators: Dict) -> float:
        """Calculate order block confidence with hybrid SMA+EMA validation"""
        try:
            confidence = 0.5
            
            # Volume factor (enhanced)
            avg_volume = df['volume'].mean()
            volume_ratio = candle['volume'] / avg_volume
            if volume_ratio > 2.5:
                confidence += 0.25
            elif volume_ratio > 1.8:
                confidence += 0.15
            
            # Candle strength
            body_size = abs(candle['close'] - candle['open'])
            candle_range = candle['high'] - candle['low']
            if candle_range > 0:
                body_ratio = body_size / candle_range
                if body_ratio > 0.8:  # Very strong body
                    confidence += 0.20
                elif body_ratio > 0.6:
                    confidence += 0.10
            
            # Hybrid SMA+EMA confluence
            trend_alignment = indicators.get('trend_alignment', 'neutral')
            entry_readiness = indicators.get('entry_readiness', 'not_ready')
            
            # SMA structure confirmation (70% weight)
            if ((ob_type == 'bullish' and trend_alignment in ['bullish', 'strong_bullish']) or
                (ob_type == 'bearish' and trend_alignment in ['bearish', 'strong_bearish'])):
                confidence += 0.15
            
            # EMA timing confirmation (30% weight)
            if ((ob_type == 'bullish' and entry_readiness in ['buy_ready', 'bullish_setup']) or
                (ob_type == 'bearish' and entry_readiness in ['sell_ready', 'bearish_setup'])):
                confidence += 0.10
            
            # RSI confluence
            rsi = indicators.get('rsi', 50)
            if ob_type == 'bullish' and rsi < 45:
                confidence += 0.08
            elif ob_type == 'bearish' and rsi > 55:
                confidence += 0.08
            
            # MACD confluence
            macd_trend = indicators.get('macd_signal_trend', 'neutral')
            if (ob_type == 'bullish' and macd_trend == 'bullish') or \
               (ob_type == 'bearish' and macd_trend == 'bearish'):
                confidence += 0.07
            
            return min(confidence, 1.0)
            
        except Exception as e:
            self.logger.error(f"Error calculating hybrid OB confidence: {e}")
            return 0.5
    
    def check_discount_premium(self, df: pd.DataFrame, indicators: Dict) -> Dict:
        """Enhanced discount/premium analysis with hybrid confirmation"""
        try:
            lookback = min(50, len(df))
            recent_df = df.tail(lookback)
            
            swing_high = recent_df['high'].max()
            swing_low = recent_df['low'].min()
            current_price = df['close'].iloc[-1]
            
            equilibrium = (swing_high + swing_low) / 2
            range_size = swing_high - swing_low
            
            if range_size == 0:
                return {
                    'territory': 'equilibrium',
                    'current_price': current_price,
                    'percentage_in_range': 50
                }
            
            # Enhanced Fibonacci levels
            discount_zone = swing_low + (range_size * 0.382)  # 38.2% Fib
            premium_zone = swing_low + (range_size * 0.618)   # 61.8% Fib
            deep_discount = swing_low + (range_size * 0.236)  # 23.6% Fib
            deep_premium = swing_low + (range_size * 0.764)   # 76.4% Fib
            
            # Determine territory with hybrid confirmation
            if current_price < deep_discount:
                territory = 'deep_discount'
            elif current_price < discount_zone:
                territory = 'discount'
            elif current_price > deep_premium:
                territory = 'deep_premium'
            elif current_price > premium_zone:
                territory = 'premium'
            else:
                territory = 'equilibrium'
            
            # Add hybrid technical bias
            trend_alignment = indicators.get('trend_alignment', 'neutral')
            entry_readiness = indicators.get('entry_readiness', 'not_ready')
            
            technical_bias = 'neutral'
            if territory in ['discount', 'deep_discount']:
                if trend_alignment in ['bullish', 'strong_bullish'] and entry_readiness in ['buy_ready', 'bullish_setup']:
                    technical_bias = 'strong_discount_with_confirmation'
            elif territory in ['premium', 'deep_premium']:
                if trend_alignment in ['bearish', 'strong_bearish'] and entry_readiness in ['sell_ready', 'bearish_setup']:
                    technical_bias = 'strong_premium_with_confirmation'
            
            return {
                'territory': territory,
                'technical_bias': technical_bias,
                'current_price': current_price,
                'swing_high': swing_high,
                'swing_low': swing_low,
                'equilibrium': equilibrium,
                'percentage_in_range': ((current_price - swing_low) / range_size) * 100,
                'hybrid_confirmation': trend_alignment != 'neutral' and entry_readiness != 'not_ready'
            }
            
        except Exception as e:
            self.logger.error(f"Error in discount/premium check: {e}")
            return {
                'territory': 'equilibrium',
                'current_price': df['close'].iloc[-1] if not df.empty else 0,
                'percentage_in_range': 50
            }
    
    def detect_manipulation_phase(self, df: pd.DataFrame, indicators: Dict) -> Dict:
        """Enhanced manipulation phase detection with hybrid analysis"""
        try:
            recent_df = df.tail(20)
            atr = indicators.get('atr', recent_df['high'].subtract(recent_df['low']).mean())
            
            range_high = recent_df['high'].max()
            range_low = recent_df['low'].min()
            range_size = range_high - range_low
            
            # Enhanced manipulation detection with hybrid confirmation
            tolerance = atr * 0.25 if atr > 0 else range_size * 0.008  # Tighter tolerance
            high_touches = sum(1 for high in recent_df['high'] if abs(high - range_high) <= tolerance)
            low_touches = sum(1 for low in recent_df['low'] if abs(low - range_low) <= tolerance)
            
            # Volume spike analysis
            avg_volume = recent_df['volume'].mean()
            volume_spikes = sum(1 for vol in recent_df['volume'] if vol > avg_volume * 1.6)
            
            # Hybrid confirmation factors
            structure_strength = indicators.get('structure_strength', 'weak')
            hybrid_confidence = indicators.get('hybrid_confidence', 0.5)
            
            # Enhanced manipulation criteria
            base_manipulation = (high_touches >= 2 and low_touches >= 2 and range_size < atr * 5)
            volume_confirmation = volume_spikes >= 2
            hybrid_confirmation = structure_strength in ['strong', 'very_strong'] and hybrid_confidence > 0.6
            
            is_manipulation = base_manipulation and (volume_confirmation or hybrid_confirmation)
            
            return {
                'is_manipulation_phase': is_manipulation,
                'range_high': range_high,
                'range_low': range_low,
                'range_size': range_size,
                'atr': atr,
                'high_touches': high_touches,
                'low_touches': low_touches,
                'volume_spikes': volume_spikes,
                'hybrid_confirmation': hybrid_confirmation,
                'confidence_score': hybrid_confidence
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting manipulation phase: {e}")
            return {
                'is_manipulation_phase': False,
                'range_high': 0, 'range_low': 0, 'range_size': 0,
                'atr': 0, 'high_touches': 0, 'low_touches': 0,
                'volume_spikes': 0, 'hybrid_confirmation': False,
                'confidence_score': 0.5
            }
    
    def analyze_single_coin(self, symbol: str) -> Dict:
        """Analyze single coin with hybrid SMA+EMA approach"""
        try:
            self.logger.info(f"Analyzing {symbol} with Hybrid SMA+EMA...")
            
            # Fetch market data
            df = self.fetch_ohlcv(symbol, '4h', 100)
            if df.empty:
                return {'error': f'No data available for {symbol}'}
            
            # Get additional market info
            market_data = self.get_market_data(symbol)
            
            # Calculate hybrid indicators
            indicators = self.calculate_technical_indicators(df.copy())
            
            # Perform analysis with hybrid approach
            structure = self.detect_market_structure(df)
            order_blocks = self.detect_order_blocks(df, structure, indicators)
            discount_premium = self.check_discount_premium(df, indicators)
            manipulation = self.detect_manipulation_phase(df, indicators)
            
            # Generate signal with hybrid confirmation
            signal = self.generate_trading_signal_hybrid(
                df, structure, order_blocks, discount_premium, 
                manipulation, indicators, market_data
            )
            
            signal['symbol'] = symbol
            signal['analysis'].update(market_data)
            
            hybrid_score = indicators.get('hybrid_confidence', 0.5)
            self.logger.info(f"{symbol} analysis complete: {signal['action']} ({signal['confidence']:.2f}) - Hybrid: {hybrid_score:.2f}")
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol}: {e}")
            return {'error': str(e), 'symbol': symbol}
    
    def generate_trading_signal_hybrid(self, df: pd.DataFrame, structure: Dict, order_blocks: List,
                                     discount_premium: Dict, manipulation: Dict, indicators: Dict,
                                     market_data: Dict) -> Dict:
        """Enhanced signal generation with hybrid SMA+EMA confirmation"""
        
        signal = {
            'timestamp': datetime.now(),
            'exchange': 'kucoin',
            'strategy_version': 'hybrid_sma_ema_v2.1',
            'action': 'hold',
            'confidence': 0.0,
            'entry_price': 0.0,
            'stop_loss': 0.0,
            'take_profit': 0.0,
            'risk_reward_ratio': 0.0,
            'analysis': {
                'current_price': df['close'].iloc[-1],
                'structure': structure,
                'order_blocks': order_blocks,
                'discount_premium': discount_premium,
                'manipulation': manipulation,
                'indicators': indicators
            }
        }
        
        current_price = df['close'].iloc[-1]
        config = self.config.get('trading_config', {})
        strategy_params = config.get('strategy_parameters', {})
        
        # Enhanced thresholds for hybrid approach
        confidence_threshold = strategy_params.get('order_block_confidence_threshold', 0.70)
        min_signal_confidence = strategy_params.get('min_confidence_for_signal', 0.75)
        
        # Hybrid confirmation requirements
        trend_alignment = indicators.get('trend_alignment', 'neutral')
        entry_readiness = indicators.get('entry_readiness', 'not_ready')
        structure_strength = indicators.get('structure_strength', 'weak')
        hybrid_confidence = indicators.get('hybrid_confidence', 0.5)
        
        # BUY Signal Logic with Hybrid Confirmation
        if (discount_premium['territory'] in ['discount', 'deep_discount'] and
            len(order_blocks) > 0 and
            manipulation['is_manipulation_phase'] and
            hybrid_confidence >= 0.65):  # Hybrid threshold
            
            bullish_obs = [ob for ob in order_blocks if ob['type'] == 'bullish' and 
                          ob['confidence'] >= confidence_threshold]
            
            if bullish_obs:
                best_ob = max(bullish_obs, key=lambda x: x['confidence'])
                
                # Enhanced hybrid confirmation scoring
                hybrid_score = 0.5  # Base score
                
                # SMA structure confirmation (70% weight)
                if trend_alignment in ['bullish', 'strong_bullish']:
                    hybrid_score += 0.25
                if structure_strength in ['strong', 'very_strong']:
                    hybrid_score += 0.15
                
                # EMA timing confirmation (30% weight)
                if entry_readiness in ['buy_ready', 'bullish_setup']:
                    hybrid_score += 0.15
                
                # Technical confluence
                rsi = indicators.get('rsi', 50)
                macd_trend = indicators.get('macd_signal_trend', 'neutral')
                bb_position = indicators.get('bb_position', 'N/A')
                
                if rsi < 50: hybrid_score += 0.05
                if rsi < 35: hybrid_score += 0.05  # Oversold bonus
                if macd_trend == 'bullish': hybrid_score += 0.08
                if bb_position in ['Below Lower', 'Lower Half']: hybrid_score += 0.05
                if market_data.get('volume_24h', 0) > 5000000: hybrid_score += 0.05  # Volume filter
                if discount_premium.get('hybrid_confirmation', False): hybrid_score += 0.08
                
                final_confidence = min(hybrid_score, 1.0)
                
                if final_confidence >= min_signal_confidence:
                    signal['action'] = 'buy'
                    signal['confidence'] = final_confidence
                    signal['entry_price'] = best_ob['low']
                    
                    # Enhanced risk management with hybrid ATR
                    atr = indicators.get('atr', manipulation['atr'])
                    risk_mgmt = config.get('risk_management', {})
                    sl_mult = risk_mgmt.get('stop_loss_atr_multiplier', 1.5)
                    tp_mult = risk_mgmt.get('take_profit_atr_multiplier', 3.2)  # Enhanced R:R
                    
                    signal['stop_loss'] = best_ob['low'] - (atr * sl_mult)
                    signal['take_profit'] = best_ob['low'] + (atr * tp_mult)
                    
                    if signal['entry_price'] != signal['stop_loss']:
                        signal['risk_reward_ratio'] = abs(signal['take_profit'] - signal['entry_price']) / abs(signal['entry_price'] - signal['stop_loss'])
        
        # SELL Signal Logic with Hybrid Confirmation  
        elif (discount_premium['territory'] in ['premium', 'deep_premium'] and
              len(order_blocks) > 0 and
              manipulation['is_manipulation_phase'] and
              hybrid_confidence >= 0.65):
            
            bearish_obs = [ob for ob in order_blocks if ob['type'] == 'bearish' and 
                          ob['confidence'] >= confidence_threshold]
            
            if bearish_obs:
                best_ob = max(bearish_obs, key=lambda x: x['confidence'])
                
                # Enhanced hybrid confirmation scoring
                hybrid_score = 0.5
                
                # SMA structure confirmation (70% weight)
                if trend_alignment in ['bearish', 'strong_bearish']:
                    hybrid_score += 0.25
                if structure_strength in ['strong', 'very_strong']:
                    hybrid_score += 0.15
                
                # EMA timing confirmation (30% weight)
                if entry_readiness in ['sell_ready', 'bearish_setup']:
                    hybrid_score += 0.15
                
                # Technical confluence  
                rsi = indicators.get('rsi', 50)
                macd_trend = indicators.get('macd_signal_trend', 'neutral')
                bb_position = indicators.get('bb_position', 'N/A')
                
                if rsi > 50: hybrid_score += 0.05
                if rsi > 65: hybrid_score += 0.05  # Overbought bonus
                if macd_trend == 'bearish': hybrid_score += 0.08
                if bb_position in ['Above Upper', 'Upper Half']: hybrid_score += 0.05
                if market_data.get('volume_24h', 0) > 5000000: hybrid_score += 0.05
                if discount_premium.get('hybrid_confirmation', False): hybrid_score += 0.08
                
                final_confidence = min(hybrid_score, 1.0)
                
                if final_confidence >= min_signal_confidence:
                    signal['action'] = 'sell'
                    signal['confidence'] = final_confidence
                    signal['entry_price'] = best_ob['high']
                    
                    # Enhanced risk management
                    atr = indicators.get('atr', manipulation['atr'])
                    risk_mgmt = config.get('risk_management', {})
                    sl_mult = risk_mgmt.get('stop_loss_atr_multiplier', 1.5)
                    tp_mult = risk_mgmt.get('take_profit_atr_multiplier', 3.2)
                    
                    signal['stop_loss'] = best_ob['high'] + (atr * sl_mult)
                    signal['take_profit'] = best_ob['high'] - (atr * tp_mult)
                    
                    if signal['stop_loss'] != signal['entry_price']:
                        signal['risk_reward_ratio'] = abs(signal['entry_price'] - signal['take_profit']) / abs(signal['stop_loss'] - signal['entry_price'])
        
        return signal
    
    def should_send_notification(self, signal: Dict) -> bool:
        """Enhanced notification filtering with hybrid criteria"""
        config = self.config.get('trading_config', {}).get('notification', {})
        
        if not config.get('enabled', True):
            return False
        
        action = signal.get('action', 'hold')
        confidence = signal.get('confidence', 0)
        hybrid_confidence = signal.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0)
        
        # Enhanced filtering for high-quality signals only
        if config.get('only_high_confidence', True):
            min_confidence = self.config.get('trading_config', {}).get('strategy_parameters', {}).get('min_confidence_for_signal', 0.75)
            min_hybrid = 0.65  # Hybrid confidence threshold
            
            if confidence < min_confidence or hybrid_confidence < min_hybrid:
                return False
        
        if config.get('send_individual_signals', True):
            return action in ['buy', 'sell']
            
        return False
    
    def run_multi_coin_analysis(self) -> Dict:
        """Run enhanced multi-coin analysis with hybrid approach"""
        try:
            self.logger.info("Starting Multi-Coin Hybrid Analysis v2.1...")
            
            config = self.config.get('trading_config', {})
            max_coins = config.get('max_coins_per_run', 25)
            max_workers = config.get('max_workers', 8)
            use_parallel = config.get('parallel_analysis', True)
            
            symbols_to_analyze = self.symbols[:max_coins]
            
            self.logger.info(f"Analyzing {len(symbols_to_analyze)} coins with Hybrid SMA+EMA approach using {max_workers} workers")
            
            results = {}
            
            if use_parallel:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_symbol = {
                        executor.submit(self.analyze_single_coin, symbol): symbol 
                        for symbol in symbols_to_analyze
                    }
                    
                    for future in as_completed(future_to_symbol):
                        symbol = future_to_symbol[future]
                        try:
                            result = future.result()
                            results[symbol] = result
                            
                            # Send individual notifications with enhanced filtering
                            if not result.get('error') and self.should_send_notification(result):
                                self.telegram.send_analysis_report(result, symbol)
                                
                        except Exception as e:
                            self.logger.error(f"Error processing {symbol}: {e}")
                            results[symbol] = {'error': str(e), 'symbol': symbol}
            else:
                for symbol in symbols_to_analyze:
                    result = self.analyze_single_coin(symbol)
                    results[symbol] = result
                    
                    if not result.get('error') and self.should_send_notification(result):
                        self.telegram.send_analysis_report(result, symbol)
            
            # Filter and send summary report
            valid_results = {k: v for k, v in results.items() if not v.get('error')}
            
            if self.config.get('trading_config', {}).get('notification', {}).get('send_summary_report', True):
                self.telegram.send_summary_report(valid_results)
            
            # Calculate hybrid statistics
            hybrid_scores = [r.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0) 
                           for r in valid_results.values()]
            avg_hybrid_score = np.mean(hybrid_scores) if hybrid_scores else 0
            
            self.logger.info(f"Multi-coin hybrid analysis complete: {len(valid_results)}/{len(results)} successful")
            self.logger.info(f"Average hybrid confidence: {avg_hybrid_score:.2f}")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Multi-coin analysis failed: {e}")
            
            # Send error notification
            if self.telegram.bot_token and self.telegram.chat_id:
                error_message = f"ðŸš¨ *Multi-Coin Hybrid Analysis Error*\n\nâŒ Error: {str(e)}\nðŸ• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S WIB')}\nðŸ”§ Version: Hybrid SMA+EMA v2.1"
                self.telegram.send_message(error_message)
            
            return {'error': str(e)}
    
    def save_results(self, results: Dict) -> str:
        """Save enhanced analysis results with hybrid metrics"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'multicoin_hybrid_analysis_{timestamp}.json'
            
            # Prepare results for JSON serialization
            json_results = {}
            hybrid_stats = {'total_coins': 0, 'successful_analysis': 0, 'avg_hybrid_score': 0, 'trading_signals': 0}
            
            hybrid_scores = []
            
            for symbol, result in results.items():
                if not result.get('error'):
                    json_result = result.copy()
                    if 'timestamp' in json_result:
                        json_result['timestamp'] = json_result['timestamp'].isoformat()
                    
                    # Extract hybrid metrics
                    hybrid_confidence = result.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0)
                    hybrid_scores.append(hybrid_confidence)
                    
                    if result.get('action') in ['buy', 'sell']:
                        hybrid_stats['trading_signals'] += 1
                    
                    json_results[symbol] = json_result
                    hybrid_stats['successful_analysis'] += 1
                else:
                    json_results[symbol] = result
                
                hybrid_stats['total_coins'] += 1
            
            # Calculate hybrid statistics
            hybrid_stats['avg_hybrid_score'] = np.mean(hybrid_scores) if hybrid_scores else 0
            hybrid_stats['analysis_success_rate'] = (hybrid_stats['successful_analysis'] / hybrid_stats['total_coins']) * 100
            hybrid_stats['signal_rate'] = (hybrid_stats['trading_signals'] / hybrid_stats['successful_analysis']) * 100 if hybrid_stats['successful_analysis'] > 0 else 0
            
            # Add metadata
            final_results = {
                'metadata': {
                    'version': 'Multi-Coin Hybrid SMA+EMA Analyzer v2.1',
                    'analysis_time': datetime.now().isoformat(),
                    'exchange': 'KuCoin',
                    'strategy': 'Smart Money Concepts + Hybrid Technical Analysis',
                    'hybrid_approach': {
                        'sma_weight': 0.70,
                        'ema_weight': 0.30,
                        'confidence_threshold': 0.75,
                        'hybrid_threshold': 0.65
                    }
                },
                'statistics': hybrid_stats,
                'results': json_results
            }
            
            # Convert numpy types
            def convert_types(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, pd.Timestamp):
                    return obj.isoformat()
                elif pd.isna(obj):
                    return None
                return str(obj)
            
            with open(filename, 'w') as f:
                json.dump(final_results, f, indent=2, default=convert_types)
            
            self.logger.info(f"Hybrid analysis results saved to {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")
            return ""

def main():
    """Main execution function for Multi-Coin Hybrid Analyzer v2.1"""
    print("ðŸš€ Multi-Coin Hybrid SMA+EMA Analyzer v2.1")
    print("=" * 50)
    print("ðŸ”§ Engine: KuCoin + CCXT + pandas-ta")
    print("ðŸ“Š Strategy: Smart Money Concepts + Hybrid Technical Analysis")
    print("âš–ï¸  Hybrid Approach: SMA (70%) + EMA (30%)")
    print("ðŸŽ¯ Quality Threshold: 75% confidence minimum")
    print("=" * 50)
    
    analyzer = MultiCoinHybridAnalyzer()
    
    # Run multi-coin analysis
    results = analyzer.run_multi_coin_analysis()
    
    # Save results to file
    filename = analyzer.save_results(results)
    
    # Print comprehensive summary
    valid_results = {k: v for k, v in results.items() if not v.get('error')}
    trading_signals = {k: v for k, v in valid_results.items() if v.get('action') in ['buy', 'sell']}
    
    # Calculate hybrid statistics
    hybrid_scores = [r.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0) 
                   for r in valid_results.values()]
    avg_hybrid_score = np.mean(hybrid_scores) if hybrid_scores else 0
    
    print(f"\nðŸ“Š Multi-Coin Hybrid Analysis Summary:")
    print(f"Total coins analyzed: {len(results)}")
    print(f"Successful analyses: {len(valid_results)}")
    print(f"Trading signals: {len(trading_signals)}")
    print(f"Average hybrid score: {avg_hybrid_score:.2f}")
    print(f"Success rate: {(len(valid_results)/len(results)*100):.1f}%")
    print(f"Signal rate: {(len(trading_signals)/len(valid_results)*100):.1f}%" if valid_results else "Signal rate: 0%")
    print(f"Results saved to: {filename}")
    
    # Print top hybrid trading signals
    if trading_signals:
        print(f"\nðŸŽ¯ Top Hybrid Trading Signals:")
        sorted_signals = sorted(trading_signals.items(), key=lambda x: x[1].get('confidence', 0), reverse=True)
        for symbol, signal in sorted_signals[:8]:
            coin = symbol.replace('/USDT', '')
            action = signal.get('action', 'hold').upper()
            confidence = signal.get('confidence', 0)
            hybrid_conf = signal.get('analysis', {}).get('indicators', {}).get('hybrid_confidence', 0)
            price = signal.get('analysis', {}).get('current_price', 0)
            print(f"  {action} {coin}: {confidence:.1%} confidence @ ${price:.6f} (Hybrid: {hybrid_conf:.2f})")
    
    print(f"\nðŸ”§ Hybrid System Performance:")
    print(f"SMA Weight (Structure): 70%")
    print(f"EMA Weight (Timing): 30%")
    print(f"Confidence Threshold: 75%")
    print(f"Hybrid Threshold: 65%")
    print(f"Quality Focus: High-confidence signals only")
    
    return results

if __name__ == "__main__":
    main()