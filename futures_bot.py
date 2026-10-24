import os
import json
import time
import ccxt
import pandas as pd
import ta
import requests
from datetime import datetime

# ================= TELEGRAM SETTINGS =================
TELEGRAM_BOT_TOKEN = "8930623320:AAEM6K1ZvXw9SmqU9safvjPUCpwAv8umdqc"
TELEGRAM_CHAT_ID = "8730935050"

# ================= TRADING SETTINGS ==================
TIMEFRAME = '15m'
TOP_COINS_COUNT = 30
ORDER_EXPIRY_MINUTES = 45
STATE_FILE = "active_trades.json"

SAFE_COINS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'LTC/USDT',
    'BCH/USDT', 'NEAR/USDT', 'UNI/USDT', 'ATOM/USDT', 'TRX/USDT'
]

EXCLUDED_COINS = [
    'USDC/USDT', 'FDUSD/USDT', 'USDP/USDT', 'TUSD/USDT', 'USDE/USDT',
    'SOXL/USDT', 'KORU/USDT', 'SKHYNIX/USDT', 'BZ/USDT'
]

def get_exchange():
    """Binance US-IP Block එක මගහැරීමට ස්වයංක්‍රීයව Global Futures Exchange සම්බන්ධ කරගැනීම"""
    try:
        ex = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
        ex.fetch_time()
        print("Connected directly to Binance Futures.")
        return ex
    except Exception:
        print("GitHub US Server detected. Using Bybit USDT Perpetual mirror for exact Futures prices...")
        return ccxt.bybit({'enableRateLimit': True, 'options': {'defaultType': 'linear'}})

exchange = get_exchange()

def load_active_trades():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_active_trades(trades):
    with open(STATE_FILE, "w") as f:
        json.dump(trades, f, indent=4)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def format_price(price):
    if price >= 100:
        return f"{price:.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    else:
        return f"{price:.5f}"

def calculate_smart_limit(direction, current_price, ema9, atr):
    atr_min, atr_max = atr * 0.25, atr * 0.60
    if direction == "LONG":
        if (current_price - atr_max) <= ema9 <= (current_price - atr_min):
            return (ema9 + (current_price - (atr * 0.35))) / 2
        return current_price - (atr * 0.35)
    else:
        if (current_price + atr_min) <= ema9 <= (current_price + atr_max):
            return (ema9 + (current_price + (atr * 0.35))) / 2
        return current_price + (atr * 0.35)

def check_active_trades(active_trades):
    if not active_trades:
        return active_trades

    print(f"Monitoring {len(active_trades)} Pending/Active trades...")
    completed_symbols = []
    now_ms = int(time.time() * 1000)

    for symbol, trade in list(active_trades.items()):
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe='1m', since=trade["timestamp_ms"], limit=120)
            if not bars:
                continue

            tag = "🛡️ SAFE COIN" if trade["is_safe"] else "🔥 TRENDING COIN"
            entry = trade["entry"]
            p_entry, p_tp1, p_tp2, p_sl = format_price(entry), format_price(trade["tp1"]), format_price(trade["tp2"]), format_price(trade["sl"])

            for bar in bars:
                bar_time, _, bar_high, bar_low, _, _ = bar
                if bar_time < trade["timestamp_ms"]:
                    continue

                if not trade["entry_hit"]:
                    if trade["type"] == "LONG":
                        if bar_low <= entry:
                            trade["entry_hit"] = True
                            send_telegram_message(
                                f"⚡ <b>LIMIT ORDER TRIGGERED! (LONG)</b> ⚡\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"✅ Price dropped to Limit Entry (<code>{p_entry}</code>).\n"
                                f"🎯 <b>TP1:</b> {p_tp1} | 🎯 <b>TP2:</b> {p_tp2} | 🛑 <b>SL:</b> {p_sl}"
                            )
                            continue
                        elif bar_high >= trade["tp1"]:
                            send_telegram_message(
                                f"❌ <b>LIMIT ORDER CANCELLED (MISSED)</b> ❌\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')}\n"
                                f"⚠️ Price reached TP1 ({p_tp1}) without touching Limit Entry ({p_entry}).\n"
                                f"🗑️ <i>Please cancel this Limit Order on Binance!</i>"
                            )
                            completed_symbols.append(symbol)
                            break

                    elif trade["type"] == "SHORT":
                        if bar_high >= entry:
                            trade["entry_hit"] = True
                            send_telegram_message(
                                f"⚡ <b>LIMIT ORDER TRIGGERED! (SHORT)</b> ⚡\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"✅ Price rose to Limit Entry (<code>{p_entry}</code>).\n"
                                f"🎯 <b>TP1:</b> {p_tp1} | 🎯 <b>TP2:</b> {p_tp2} | 🛑 <b>SL:</b> {p_sl}"
                            )
                            continue
                        elif bar_low <= trade["tp1"]:
                            send_telegram_message(
                                f"❌ <b>LIMIT ORDER CANCELLED (MISSED)</b> ❌\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')}\n"
                                f"⚠️ Price dropped to TP1 ({p_tp1}) without touching Limit Entry ({p_entry}).\n"
                                f"🗑️ <i>Please cancel this Limit Order on Binance!</i>"
                            )
                            completed_symbols.append(symbol)
                            break
                else:
                    if trade["type"] == "LONG":
                        if bar_low <= trade["sl"]:
                            loss_pct = abs((trade["sl"] - entry) / entry * 100)
                            send_telegram_message(
                                f"🛑 <b>STOP LOSS HIT!</b> 🛑\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"📈 <b>LONG</b> | 💰 <b>Entry:</b> {p_entry} | 🛑 <b>SL:</b> {p_sl}\n"
                                f"📉 <b>Loss:</b> -{loss_pct:.2f}% (1x)"
                            )
                            completed_symbols.append(symbol)
                            break
                        elif bar_high >= trade["tp2"]:
                            profit_pct = abs((trade["tp2"] - entry) / entry * 100)
                            send_telegram_message(
                                f"🎯🎯 <b>TAKE PROFIT 2 ACHIEVED!</b> 🎯🎯\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"📈 <b>LONG</b> | 💰 <b>Entry:</b> {p_entry} | 🎯 <b>TP2:</b> {p_tp2}\n"
                                f"💵 <b>Profit:</b> +{profit_pct:.2f}% (At 10x = +{profit_pct*10:.1f}%)"
                            )
                            completed_symbols.append(symbol)
                            break
                        elif bar_high >= trade["tp1"] and not trade["tp1_hit"]:
                            profit_pct = abs((trade["tp1"] - entry) / entry * 100)
                            trade["tp1_hit"] = True
                            send_telegram_message(
                                f"✅ <b>TAKE PROFIT 1 HIT!</b> ✅\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"📈 <b>LONG</b> | 💰 <b>Entry:</b> {p_entry} | 🎯 <b>TP1:</b> {p_tp1}\n"
                                f"💵 <b>Profit:</b> +{profit_pct:.2f}% (At 10x = +{profit_pct*10:.1f}%)\n"
                                f"💡 <i>Book 50% profit & move SL to Entry ({p_entry})!</i>"
                            )

                    elif trade["type"] == "SHORT":
                        if bar_high >= trade["sl"]:
                            loss_pct = abs((trade["sl"] - entry) / entry * 100)
                            send_telegram_message(
                                f"🛑 <b>STOP LOSS HIT!</b> 🛑\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"📉 <b>SHORT</b> | 💰 <b>Entry:</b> {p_entry} | 🛑 <b>SL:</b> {p_sl}\n"
                                f"📉 <b>Loss:</b> -{loss_pct:.2f}% (1x)"
                            )
                            completed_symbols.append(symbol)
                            break
                        elif bar_low <= trade["tp2"]:
                            profit_pct = abs((entry - trade["tp2"]) / entry * 100)
                            send_telegram_message(
                                f"🎯🎯 <b>TAKE PROFIT 2 ACHIEVED!</b> 🎯🎯\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"📉 <b>SHORT</b> | 💰 <b>Entry:</b> {p_entry} | 🎯 <b>TP2:</b> {p_tp2}\n"
                                f"💵 <b>Profit:</b> +{profit_pct:.2f}% (At 10x = +{profit_pct*10:.1f}%)"
                            )
                            completed_symbols.append(symbol)
                            break
                        elif bar_low <= trade["tp1"] and not trade["tp1_hit"]:
                            profit_pct = abs((entry - trade["tp1"]) / entry * 100)
                            trade["tp1_hit"] = True
                            send_telegram_message(
                                f"✅ <b>TAKE PROFIT 1 HIT!</b> ✅\n━━━━━━━━━━━━━━━━━━━━\n"
                                f"🪙 <b>Coin:</b> #{symbol.replace('/', '')} ({tag})\n"
                                f"📉 <b>SHORT</b> | 💰 <b>Entry:</b> {p_entry} | 🎯 <b>TP1:</b> {p_tp1}\n"
                                f"💵 <b>Profit:</b> +{profit_pct:.2f}% (At 10x = +{profit_pct*10:.1f}%)\n"
                                f"💡 <i>Book 50% profit & move SL to Entry ({p_entry})!</i>"
                            )

            if symbol not in completed_symbols and not trade["entry_hit"]:
                if ((now_ms - trade["timestamp_ms"]) / 60000) >= ORDER_EXPIRY_MINUTES:
                    send_telegram_message(
                        f"⌛ <b>LIMIT ORDER EXPIRED ({ORDER_EXPIRY_MINUTES}m)</b> ⌛\n━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>Coin:</b> #{symbol.replace('/', '')}\n"
                        f"⚠️ Market did not touch Limit Entry (<code>{p_entry}</code>) within {ORDER_EXPIRY_MINUTES}m.\n"
                        f"🗑️ <i>Please cancel this pending Limit Order on Binance!</i>"
                    )
                    completed_symbols.append(symbol)

            time.sleep(0.2)
        except Exception as e:
            print(f"Error tracking {symbol}: {e}")

    for sym in completed_symbols:
        del active_trades[sym]

    return active_trades

def get_top_volume_symbols(limit=30):
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = []
        for symbol, data in tickers.items():
            if '/USDT:USDT' in symbol and data.get('quoteVolume') is not None:
                clean_symbol = symbol.split(':')[0]
                if clean_symbol not in EXCLUDED_COINS:
                    usdt_pairs.append((clean_symbol, data['quoteVolume']))
        usdt_pairs.sort(key=lambda x: x[1], reverse=True)
        return [pair[0] for pair in usdt_pairs[:limit]]
    except Exception as e:
        print(f"Error fetching top coins: {e}")
        return []

def analyze_symbol(symbol, is_safe, active_trades):
    if symbol in active_trades:
        return

    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=250)
        if len(bars) < 210:
            return

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['EMA200'] = ta.trend.ema_indicator(df['close'], window=200)
        df['EMA9'] = ta.trend.ema_indicator(df['close'], window=9)
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        df['VOL_SMA20'] = df['volume'].rolling(window=20).mean()
        
        macd_ind = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD'] = macd_ind.macd()
        df['MACD_SIGNAL'] = macd_ind.macd_signal()
        
        atr_ind = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14)
        df['ATR'] = atr_ind.average_true_range()

        closed_curr, closed_prev = df.iloc[-2], df.iloc[-3]
        current_price = float(df.iloc[-1]['close'])
        atr = float(closed_curr['ATR'])
        ema9 = float(closed_curr['EMA9'])

        volume_ok = closed_curr['volume'] >= (closed_curr['VOL_SMA20'] * 0.85)

        long_condition = (
            current_price > closed_curr['EMA200'] and
            closed_prev['MACD'] <= closed_prev['MACD_SIGNAL'] and
            closed_curr['MACD'] > closed_curr['MACD_SIGNAL'] and
            42 < closed_curr['RSI'] < 65 and volume_ok
        )

        short_condition = (
            current_price < closed_curr['EMA200'] and
            closed_prev['MACD'] >= closed_prev['MACD_SIGNAL'] and
            closed_curr['MACD'] < closed_curr['MACD_SIGNAL'] and
            35 < closed_curr['RSI'] < 58 and volume_ok
        )

        category_header = "🛡️ <b>SAFE COIN LIMIT SIGNAL</b> 🛡️" if is_safe else "🔥 <b>TRENDING COIN LIMIT SIGNAL</b> 🔥"
        risk_note = "✅ <b>Leverage:</b> 5x - 10x (Isolated)" if is_safe else "⚠️ <b>High Volatility:</b> Use 2x - 5x Leverage!"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now_ms = int(time.time() * 1000)

        if long_condition:
            limit_entry = calculate_smart_limit("LONG", current_price, ema9, atr)
            sl, tp1, tp2 = limit_entry - (atr * 1.5), limit_entry + (atr * 2.0), limit_entry + (atr * 3.5)
            
            msg = (
                f"{category_header}\n🟢 <b>ORDER: BUY / LONG LIMIT (15m)</b> 🟢\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Coin:</b> <code>{symbol.replace('/', '')}</code>\n"
                f"📍 <b>Current Price:</b> {format_price(current_price)}\n"
                f"⏳ <b>Limit Entry:</b> <code>{format_price(limit_entry)}</code> <i>(Tap to Copy)</i>\n\n"
                f"🎯 <b>Take Profit 1:</b> <code>{format_price(tp1)}</code>\n"
                f"🎯 <b>Take Profit 2:</b> <code>{format_price(tp2)}</code>\n"
                f"🛑 <b>Stop Loss:</b> <code>{format_price(sl)}</code>\n━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>RSI:</b> {closed_curr['RSI']:.1f} | <b>Volume:</b> Strong ✅\n"
                f"⏱️ <b>Valid For:</b> {ORDER_EXPIRY_MINUTES} Mins\n{risk_note}"
            )
            send_telegram_message(msg)
            active_trades[symbol] = {
                "type": "LONG", "entry": limit_entry, "tp1": tp1, "tp2": tp2, "sl": sl,
                "entry_hit": False, "tp1_hit": False, "time": now_str, "timestamp_ms": now_ms, "is_safe": is_safe
            }

        elif short_condition:
            limit_entry = calculate_smart_limit("SHORT", current_price, ema9, atr)
            sl, tp1, tp2 = limit_entry + (atr * 1.5), limit_entry - (atr * 2.0), limit_entry - (atr * 3.5)
            
            msg = (
                f"{category_header}\n🔴 <b>ORDER: SELL / SHORT LIMIT (15m)</b> 🔴\n━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Coin:</b> <code>{symbol.replace('/', '')}</code>\n"
                f"📍 <b>Current Price:</b> {format_price(current_price)}\n"
                f"⏳ <b>Limit Entry:</b> <code>{format_price(limit_entry)}</code> <i>(Tap to Copy)</i>\n\n"
                f"🎯 <b>Take Profit 1:</b> <code>{format_price(tp1)}</code>\n"
                f"🎯 <b>Take Profit 2:</b> <code>{format_price(tp2)}</code>\n"
                f"🛑 <b>Stop Loss:</b> <code>{format_price(sl)}</code>\n━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>RSI:</b> {closed_curr['RSI']:.1f} | <b>Volume:</b> Strong ✅\n"
                f"⏱️ <b>Valid For:</b> {ORDER_EXPIRY_MINUTES} Mins\n{risk_note}"
            )
            send_telegram_message(msg)
            active_trades[symbol] = {
                "type": "SHORT", "entry": limit_entry, "tp1": tp1, "tp2": tp2, "sl": sl,
                "entry_hit": False, "tp1_hit": False, "time": now_str, "timestamp_ms": now_ms, "is_safe": is_safe
            }

    except Exception as e:
        print(f"Error scanning {symbol}: {e}")

def run_once():
    print("☁️ Running Cloud Scan Cycle...")
    active_trades = load_active_trades()
    
    # 1. මුලින්ම කලින් තිබුණු ට්‍රේඩ් වල TP/SL පරීක්ෂා කිරීම
    active_trades = check_active_trades(active_trades)
    
    # 2. අලුත් සිග්නල් සෙවීම
    for symbol in SAFE_COINS:
        analyze_symbol(symbol, is_safe=True, active_trades=active_trades)
        time.sleep(0.2)
        
    top_symbols = get_top_volume_symbols(TOP_COINS_COUNT)
    trending_only = [s for s in top_symbols if s not in SAFE_COINS]
    
    for symbol in trending_only:
        analyze_symbol(symbol, is_safe=False, active_trades=active_trades)
        time.sleep(0.2)
        
    # 3. Active Trades ටික ඊළඟ වටය සඳහා Save කිරීම
    save_active_trades(active_trades)
    print("✅ Cloud Scan Complete!")

if __name__ == "__main__":
    run_once()
