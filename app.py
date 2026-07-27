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

# ===================================================
# 🔒 APPROVED USERS & PASSWORDS LIST
# ===================================================
APPROVED_USERS = {
    "ranadigitalhub555@gmail.com": "user1234",
    "irfanghauri052@gmail.com": "user1234"
}

@app.route('/')
def home():
    return "Forex Pro Live Signal Server is Running Perfectly! 🚀"

# ---------------------------------------------------------
# 🔑 LOGIN ROUTE
# ---------------------------------------------------------
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()

        if email in APPROVED_USERS and APPROVED_USERS[email] == password:
            return jsonify({
                "status": "success",
                "message": "Access Granted! Welcome to Forex Signals."
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Access Denied: Email approved nahi hai ya password galat hai."
            }), 401

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------------------------------------------------
# 🧮 FAST LOCAL INDICATOR CALCULATOR
# ---------------------------------------------------------
def calculate_local_indicators(price_list):
    df = pd.DataFrame({'close': price_list})
    close = df['close']
    
    # 1. RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # 2. MACD (12, 26, 9)
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    
    # 3. Bollinger Bands (20, 2)
    middle_band = close.rolling(window=20).mean()
    std = close.rolling(window=20).std()
    upper_band = middle_band + (std * 2)
    lower_band = middle_band - (std * 2)
    
    return {
        "price": float(close.iloc[-1]),
        "rsi": float(rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50.0),
        "macd_line": float(macd_line.iloc[-1] if not np.isnan(macd_line.iloc[-1]) else 0.0),
        "macd_signal": float(macd_signal.iloc[-1] if not np.isnan(macd_signal.iloc[-1]) else 0.0),
        "prev_macd_line": float(macd_line.iloc[-2] if not np.isnan(macd_line.iloc[-2]) else 0.0),
        "prev_macd_signal": float(macd_signal.iloc[-2] if not np.isnan(macd_signal.iloc[-2]) else 0.0),
        "upper_band": float(upper_band.iloc[-1] if not np.isnan(upper_band.iloc[-1]) else close.iloc[-1]),
        "lower_band": float(lower_band.iloc[-1] if not np.isnan(lower_band.iloc[-1]) else close.iloc[-1])
    }

# ---------------------------------------------------------
# 🌐 DUAL TWELVEDATA FETCH LOGIC
# ---------------------------------------------------------
def get_twelvedata_candles(coin, timeframe, api_key):
    url = f"https://api.twelvedata.com/time_series?symbol={coin}&interval={timeframe}&outputsize=40&apikey={api_key}"
    res = requests.get(url, timeout=3.5).json()
    
    if "values" in res and len(res["values"]) > 20:
        # Reversing list so oldest is first, newest is last
        prices = [float(x['close']) for x in reversed(res['values'])]
        return prices
    return None

def fetch_market_data(coin, timeframe):
    # 1️⃣ TRY PRIMARY KEY
    try:
        prices = get_twelvedata_candles(coin, timeframe, KEY_PRIMARY)
        if prices:
            print("🟢 Fetched using Primary TwelveData Key")
            return calculate_local_indicators(prices)
        else:
            print("⚠️ Primary Key limit hit, switching to Secondary Key...")
    except Exception as e:
        print(f"⚠️ Primary Key Error: {e}")

    # 2️⃣ TRY SECONDARY KEY (FALLBACK)
    try:
        prices = get_twelvedata_candles(coin, timeframe, KEY_SECONDARY)
        if prices:
            print("🟡 Fetched using Secondary TwelveData Key")
            return calculate_local_indicators(prices)
        else:
            print("⚠️ Secondary Key limit hit or empty data.")
    except Exception as e:
        print(f"⚠️ Secondary Key Error: {e}")

    return None

# ---------------------------------------------------------
# 📊 STRATEGY ROUTE
# ---------------------------------------------------------
@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    data = fetch_market_data(coin, timeframe)
    
    if data is None:
        return jsonify({
            "status": "error",
            "message": "Dono TwelveData Keys ki limits exhaust ho chuki hain. Baki time bad try karein."
        }), 500

    latest_price = data['price']
    latest_rsi = round(data['rsi'], 2)
    macd_line = data['macd_line']
    macd_signal = data['macd_signal']
    prev_macd_line = data['prev_macd_line']
    prev_macd_signal = data['prev_macd_signal']
    upper_band = data['upper_band']
    lower_band = data['lower_band']

    # Strategy Logic Conditions
    macd_bullish = (prev_macd_line <= prev_macd_signal) and (macd_line > macd_signal)
    macd_bearish = (prev_macd_line >= prev_macd_signal) and (macd_line < macd_signal)
    
    price_at_lower_band = latest_price <= lower_band
    price_at_upper_band = latest_price >= upper_band

    signal = "WAIT (NEUTRAL) 🟡"
    confidence = "LOW"
    action_type = "NO_ACTION"

    # --- CALL LOGIC ---
    if (latest_rsi < 30) and macd_bullish and price_at_lower_band:
        signal = "STRONG CALL 🟢 (RSI + MACD + BB Bounce)"
        confidence = "HIGH"
        action_type = "CALL"

    # --- PUT LOGIC ---
    elif (latest_rsi > 70) and macd_bearish and price_at_upper_band:
        signal = "STRONG PUT 🔴 (RSI + MACD + BB Rejection)"
        confidence = "HIGH"
        action_type = "PUT"
        
    elif (latest_rsi < 35) and macd_bullish:
        signal = "WEAK CALL 🟢"
        confidence = "MEDIUM"
        action_type = "CALL"

    elif (latest_rsi > 65) and macd_bearish:
        signal = "WEAK PUT 🔴"
        confidence = "MEDIUM"
        action_type = "PUT"

    return jsonify({
        "status": "success",
        "coin": coin,
        "timeframe": timeframe,
        "current_price": round(latest_price, 5),
        "indicators": {
            "rsi": latest_rsi,
            "macd_line": round(macd_line, 5),
            "macd_signal": round(macd_signal, 5),
            "bb_upper": round(upper_band, 5),
            "bb_lower": round(lower_band, 5)
        },
        "signal": signal,
        "action": action_type,
        "confidence": confidence
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
