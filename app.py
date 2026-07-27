from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
CORS(app)

# ===================================================
# 🔑 TWELVE DATA DUAL API KEYS
# ===================================================
KEY_PRIMARY = os.environ.get("TWELVE_DATA_KEY_1", "a592dba7321442efa229bee2b8a1cff8")
KEY_SECONDARY = os.environ.get("TWELVE_DATA_KEY_2", "5f98e9f032684d27b8b266656bfcadac")

APPROVED_USERS = {
    "ranadigitalhub555@gmail.com": "user1234",
    "irfanghauri052@gmail.com": "user1234"
}

@app.route('/')
def home():
    return "Forex Pro Scoring Engine Server Live! 🚀"

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()

        if email in APPROVED_USERS and APPROVED_USERS[email] == password:
            return jsonify({"status": "success", "message": "Access Granted!"}), 200
        return jsonify({"status": "error", "message": "Access Denied"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------------------------------------------------
# 📊 ADVANCED DATA & INDICATORS CALCULATOR
# ---------------------------------------------------------
def process_market_data(ohlc_df):
    df = ohlc_df.copy()
    close = df['close']
    high = df['high']
    low = df['low']
    open_p = df['open']
    volume = df['volume']

    # 1. EMAs (20 & 50) - Trend Filter (25 Points)
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()

    # 2. RSI (14) - Momentum (15 Points)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # 3. MACD (12, 26, 9) - Crossover/Confirmation (20 Points)
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()

    # 4. ADX (Trend Strength Filter > 18)
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    up_move = high - high.shift()
    down_move = low.shift() - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
    
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(14).mean()

    # 5. Support & Resistance (15 Points)
    recent_high = high.iloc[-20:-1].max()
    recent_low = low.iloc[-20:-1].min()

    # 6. Volume Confirmation (15 Points)
    avg_volume = volume.rolling(10).mean()
    vol_spike = volume.iloc[-1] > avg_volume.iloc[-1]

    # 7. Candlestick Pattern (10 Points)
    curr_body = abs(close.iloc[-1] - open_p.iloc[-1])
    
    bullish_engulfing = (close.iloc[-1] > open_p.iloc[-1]) and (close.iloc[-2] < open_p.iloc[-2]) and (close.iloc[-1] >= open_p.iloc[-2])
    bearish_engulfing = (close.iloc[-1] < open_p.iloc[-1]) and (close.iloc[-2] > open_p.iloc[-2]) and (close.iloc[-1] <= open_p.iloc[-2])
    
    candle_wick_bottom = min(open_p.iloc[-1], close.iloc[-1]) - low.iloc[-1]
    candle_wick_top = high.iloc[-1] - max(open_p.iloc[-1], close.iloc[-1])
    
    bullish_pinbar = candle_wick_bottom > (curr_body * 2)
    bearish_pinbar = candle_wick_top > (curr_body * 2)

    return {
        "price": float(close.iloc[-1]),
        "ema_20": float(ema_20.iloc[-1]),
        "ema_50": float(ema_50.iloc[-1]),
        "rsi": float(rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50.0),
        "macd_line": float(macd_line.iloc[-1]),
        "macd_signal": float(macd_signal.iloc[-1]),
        "adx": float(adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 20.0),
        "vol_spike": bool(vol_spike),
        "recent_high": float(recent_high),
        "recent_low": float(recent_low),
        "bullish_pattern": bool(bullish_engulfing or bullish_pinbar),
        "bearish_pattern": bool(bearish_engulfing or bearish_pinbar),
        "atr": float(atr.iloc[-1] if not np.isnan(atr.iloc[-1]) else 0.0005)
    }

def fetch_twelvedata_ohlc(coin, timeframe, api_key):
    url = f"https://api.twelvedata.com/time_series?symbol={coin}&interval={timeframe}&outputsize=60&apikey={api_key}"
    res = requests.get(url, timeout=3.5).json()
    if "values" in res and len(res["values"]) > 30:
        data = res["values"]
        df = pd.DataFrame(data)
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float) if 'volume' in df and 'volume' in df.columns else 100.0
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    return None

# ---------------------------------------------------------
# 📊 HIGH-FREQUENCY WEIGHTED SCORING STRATEGY ROUTE
# ---------------------------------------------------------
@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    # 1️⃣ Dual Key Data Fetching
    df = fetch_twelvedata_ohlc(coin, timeframe, KEY_PRIMARY)
    if df is None:
        df = fetch_twelvedata_ohlc(coin, timeframe, KEY_SECONDARY)
        
    if df is None:
        return jsonify({"status": "error", "message": "Dono API Keys ki limits end ho chuki hain."}), 500

    data = process_market_data(df)
    
    price = data['price']
    rsi = round(data['rsi'], 2)
    atr = data['atr']
    
    buy_score = 0
    sell_score = 0
    reasons = []

    # 1. EMA Trend (25 Points)
    if data['ema_20'] > data['ema_50']:
        buy_score += 25
        reasons.append("EMA 20 > 50 Bullish")
    elif data['ema_20'] < data['ema_50']:
        sell_score += 25
        reasons.append("EMA 20 < 50 Bearish")

    # 2. MACD Confirmation (20 Points)
    if data['macd_line'] > data['macd_signal']:
        buy_score += 20
        reasons.append("MACD Bullish")
    else:
        sell_score += 20
        reasons.append("MACD Bearish")

    # 3. RSI Direction (15 Points)
    if rsi > 55:
        buy_score += 15
        reasons.append("RSI > 55")
    elif rsi < 45:
        sell_score += 15
        reasons.append("RSI < 45")

    # 4. Volume Spike (15 Points)
    if data['vol_spike']:
        buy_score += 15
        sell_score += 15
        reasons.append("High Volume")

    # 5. Support & Resistance (15 Points)
    if price <= (data['recent_low'] * 1.0005):
        buy_score += 15
        reasons.append("At Support Level")
    elif price >= (data['recent_high'] * 0.9995):
        sell_score += 15
        reasons.append("At Resistance Level")

    # 6. Candlestick Patterns (10 Points)
    if data['bullish_pattern']:
        buy_score += 10
        reasons.append("Bullish Candle Pattern")
    elif data['bearish_pattern']:
        sell_score += 10
        reasons.append("Bearish Candle Pattern")

    # ADX Boost Filter (>18)
    if data['adx'] > 18:
        if buy_score > sell_score: buy_score = min(buy_score + 5, 100)
        if sell_score > buy_score: sell_score = min(sell_score + 5, 100)

    # ---------------------------------------------------------
    # FINAL DECISION LOGIC (Minimizes NEUTRAL)
    # ---------------------------------------------------------
    signal = "WAIT (NEUTRAL) 🟡"
    confidence = max(buy_score, sell_score)
    action_type = "NO_ACTION"
    tp = price
    sl = price

    if buy_score >= 70 and buy_score > sell_score:
        signal = "STRONG BUY 🟢"
        action_type = "CALL"
        sl = round(price - (atr * 1.5), 5)
        tp = round(price + (atr * 2.5), 5)

    elif sell_score >= 70 and sell_score > buy_score:
        signal = "STRONG SELL 🔴"
        action_type = "PUT"
        sl = round(price + (atr * 1.5), 5)
        tp = round(price - (atr * 2.5), 5)

    elif buy_score >= 55 and buy_score > sell_score:
        signal = "BUY 🟢"
        action_type = "CALL"
        sl = round(price - (atr * 1.2), 5)
        tp = round(price + (atr * 1.8), 5)

    elif sell_score >= 55 and sell_score > buy_score:
        signal = "SELL 🔴"
        action_type = "PUT"
        sl = round(price + (atr * 1.2), 5)
        tp = round(price - (atr * 1.8), 5)

    return jsonify({
        "status": "success",
        "coin": coin,
        "timeframe": timeframe,
        "entry_price": round(price, 5),
        "signal": signal,
        "action": action_type,
        "confidence": f"{confidence}%",
        "take_profit": tp,
        "stop_loss": sl,
        "indicators": {
            "rsi": rsi,
            "adx": round(data['adx'], 2),
            "ema_20": round(data['ema_20'], 5),
            "ema_50": round(data['ema_50'], 5)
        },
        "reason": " + ".join(reasons[:3]) if reasons else "Market Directionless"
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
