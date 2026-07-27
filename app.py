from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
CORS(app)

# ===================================================
# 🔑 API KEYS SETTINGS
# ===================================================
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_API_KEY", "a592dba7321442efa229bee2b8a1cff8")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "d9jm151r01qr77bn79sgd9jm151r01qr77bn79t0")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "I21UDS2THP8Z1CWN")

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
# 🔑 LOGIN ROUTE FOR EXTENSION
# ---------------------------------------------------------
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

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
# 🧮 LOCAL TECHNICAL INDICATOR CALCULATOR (FALLBACK SUPPORT)
# ---------------------------------------------------------
def calculate_local_indicators(df):
    """Raw OHLC Data se RSI, MACD, aur Bollinger Bands calculate karne ke liye"""
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
        "rsi": float(rsi.iloc[-1]),
        "macd_line": float(macd_line.iloc[-1]),
        "macd_signal": float(macd_signal.iloc[-1]),
        "prev_macd_line": float(macd_line.iloc[-2]),
        "prev_macd_signal": float(macd_signal.iloc[-2]),
        "upper_band": float(upper_band.iloc[-1]),
        "lower_band": float(lower_band.iloc[-1]),
        "middle_band": float(middle_band.iloc[-1])
    }

# ---------------------------------------------------------
# 🌐 MULTI-API FAILOVER DATA FETCH
# ---------------------------------------------------------
def get_market_indicators(coin, timeframe):
    # 1️⃣ TRY TWELVEDATA (PRIMARY)
    try:
        rsi_url = f"https://api.twelvedata.com/rsi?symbol={coin}&interval={timeframe}&time_period=14&apikey={TWELVE_DATA_KEY}"
        macd_url = f"https://api.twelvedata.com/macd?symbol={coin}&interval={timeframe}&apikey={TWELVE_DATA_KEY}"
        bbands_url = f"https://api.twelvedata.com/bbands?symbol={coin}&interval={timeframe}&time_period=20&sd=2&apikey={TWELVE_DATA_KEY}"
        price_url = f"https://api.twelvedata.com/price?symbol={coin}&apikey={TWELVE_DATA_KEY}"

        rsi_res = requests.get(rsi_url, timeout=4).json()
        macd_res = requests.get(macd_url, timeout=4).json()
        bbands_res = requests.get(bbands_url, timeout=4).json()
        price_res = requests.get(price_url, timeout=4).json()

        if ("values" in rsi_res and "values" in macd_res and "values" in bbands_res and "price" in price_res):
            print("🟢 Data fetched using TwelveData")
            return {
                "price": float(price_res['price']),
                "rsi": float(rsi_res['values'][0]['rsi']),
                "macd_line": float(macd_res['values'][0]['macd']),
                "macd_signal": float(macd_res['values'][0]['macd_signal']),
                "prev_macd_line": float(macd_res['values'][1]['macd']),
                "prev_macd_signal": float(macd_res['values'][1]['macd_signal']),
                "upper_band": float(bbands_res['values'][0]['upper_band']),
                "lower_band": float(bbands_res['values'][0]['lower_band']),
                "middle_band": float(bbands_res['values'][0]['middle_band'])
            }
    except Exception as e:
        print(f"⚠️ TwelveData limit/error: {e}")

    # 2️⃣ TRY FINNHUB (FALLBACK 1)
    try:
        # Finnhub Symbol Mapping
        fh_symbol = "OANDA:" + coin.replace("/", "_")
        if "XAU" in coin:
            fh_symbol = "OANDA:XAU_USD"
            
        tf_map = {'1min': '1', '5min': '5', '15min': '15', '1h': '60'}
        resolution = tf_map.get(timeframe, '1')
        
        # Candles Data
        import time
        to_time = int(time.time())
        from_time = to_time - 3600 * 20 # Last 20 hours
        
        url = f"https://finnhub.io/api/v1/forex/candle?symbol={fh_symbol}&resolution={resolution}&from={from_time}&to={to_time}&token={FINNHUB_KEY}"
        res = requests.get(url, timeout=4).json()
        
        if res.get('s') == 'ok':
            df = pd.DataFrame({'close': res['c']})
            print("🟡 Data fetched using Finnhub (Fallback 1)")
            return calculate_local_indicators(df)
    except Exception as e:
        print(f"⚠️ Finnhub limit/error: {e}")

    # 3️⃣ TRY ALPHA VANTAGE (FALLBACK 2)
    try:
        pair = coin.split('/')
        from_symbol, to_symbol = pair[0], pair[1]
        av_url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={from_symbol}&to_symbol={to_symbol}&interval={timeframe}&apikey={ALPHA_VANTAGE_KEY}"
        
        res = requests.get(av_url, timeout=4).json()
        time_series_key = f"Time Series FX ({timeframe})"
        
        if time_series_key in res:
            data = res[time_series_key]
            df = pd.DataFrame.from_dict(data, orient='index')
            df['close'] = df['4. close'].astype(float)
            df = df.iloc[::-1] # Reverse to chronological order
            print("🟠 Data fetched using Alpha Vantage (Fallback 2)")
            return calculate_local_indicators(df)
    except Exception as e:
        print(f"⚠️ Alpha Vantage limit/error: {e}")

    # 4️⃣ TRY YAHOO FINANCE (`yfinance`) (FALLBACK 3 - UNLIMITED)
    try:
        import yfinance as yf
        yf_symbol = coin.replace("/", "") + "=X"
        if "XAU" in coin:
            yf_symbol = "GC=F"

        df = yf.download(tickers=yf_symbol, period="1d", interval=timeframe, progress=False)
        if not df.empty:
            df = df.rename(columns={'Close': 'close'})
            print("🔵 Data fetched using Yahoo Finance (Fallback 3)")
            return calculate_local_indicators(df)
    except Exception as e:
        print(f"⚠️ Yahoo Finance error: {e}")

    return None

# ---------------------------------------------------------
# 📊 ADVANCED STRATEGY ROUTE
# ---------------------------------------------------------
@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    data = get_market_indicators(coin, timeframe)
    
    if data is None:
        return jsonify({
            "status": "error",
            "message": "All API limits are exhausted or server connectivity issue."
        }), 500

    latest_price = data['price']
    latest_rsi = data['rsi']
    macd_line = data['macd_line']
    macd_signal = data['macd_signal']
    prev_macd_line = data['prev_macd_line']
    prev_macd_signal = data['prev_macd_signal']
    upper_band = data['upper_band']
    lower_band = data['lower_band']

    # --- STRATEGY LOGIC ---
    macd_bullish = (prev_macd_line <= prev_macd_signal) and (macd_line > macd_signal)
    macd_bearish = (prev_macd_line >= prev_macd_signal) and (macd_line < macd_signal)
    
    price_at_lower_band = latest_price <= lower_band
    price_at_upper_band = latest_price >= upper_band

    signal = "WAIT (NEUTRAL) 🟡"
    confidence = "LOW"
    action_type = "NO_ACTION"

    if (latest_rsi < 30) and macd_bullish and price_at_lower_band:
        signal = "STRONG CALL 🟢 (RSI + MACD + BB Bounce)"
        confidence = "HIGH"
        action_type = "CALL"

    elif (latest_rsi > 70) and macd_bearish and price_at_upper_band:
        signal = "STRONG PUT 🔴 (RSI + MACD + BB Rejection)"
        confidence = "HIGH"
        action_type = "PUT"
        
    elif (latest_rsi < 35) and macd_bullish:
        signal = "WEAK CALL 🟢 (Waiting for BB Bounce)"
        confidence = "MEDIUM"
        action_type = "CALL"

    elif (latest_rsi > 65) and macd_bearish:
        signal = "WEAK PUT 🔴 (Waiting for BB Rejection)"
        confidence = "MEDIUM"
        action_type = "PUT"

    return jsonify({
        "status": "success",
        "coin": coin,
        "timeframe": timeframe,
        "current_price": round(latest_price, 5),
        "indicators": {
            "rsi": round(latest_rsi, 2),
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
