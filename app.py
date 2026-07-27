from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_API_KEY", "a592dba7321442efa229bee2b8a1cff8")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "d9jm151r01qr77bn79sgd9jm151r01qr77bn79t0")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "I21UDS2THP8Z1CWN")

APPROVED_USERS = {
    "ranadigitalhub555@gmail.com": "user1234",
    "irfanghauri052@gmail.com": "user1234"
}

@app.route('/')
def home():
    return "Forex Pro Server is Live! 🚀"

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()

        if email in APPROVED_USERS and APPROVED_USERS[email] == password:
            return jsonify({"status": "success", "message": "Access Granted!"}), 200
        return jsonify({"status": "error", "message": "Invalid Credentials"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Local Safe Calculator
def calculate_from_prices(price_list):
    import pandas as pd
    import numpy as np
    
    df = pd.DataFrame({'close': price_list})
    close = df['close']
    
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    
    # Bollinger Bands
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

def get_market_data_safe(coin, timeframe):
    # --- 1. TWELVEDATA (1 Fast Call) ---
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={coin}&interval={timeframe}&outputsize=35&apikey={TWELVE_DATA_KEY}"
        res = requests.get(url, timeout=2.5).json()
        if "values" in res and len(res["values"]) > 20:
            prices = [float(x['close']) for x in reversed(res['values'])]
            return calculate_from_prices(prices)
    except Exception as e:
        print("TwelveData Fail:", e)

    # --- 2. FINNHUB ---
    try:
        import time
        fh_symbol = "OANDA:" + coin.replace("/", "_")
        if "XAU" in coin: fh_symbol = "OANDA:XAU_USD"
        
        tf_map = {'1min': '1', '5min': '5', '15min': '15', '1h': '60'}
        res_tf = tf_map.get(timeframe, '1')
        
        to_t = int(time.time())
        from_t = to_t - 3600 * 6
        
        url = f"https://finnhub.io/api/v1/forex/candle?symbol={fh_symbol}&resolution={res_tf}&from={from_t}&to={to_t}&token={FINNHUB_KEY}"
        res = requests.get(url, timeout=2.5).json()
        
        if res.get('s') == 'ok' and len(res.get('c', [])) > 20:
            prices = [float(x) for x in res['c']]
            return calculate_from_prices(prices)
    except Exception as e:
        print("Finnhub Fail:", e)

    # --- 3. ALPHA VANTAGE ---
    try:
        pair = coin.split('/')
        av_url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={pair[0]}&to_symbol={pair[1]}&interval={timeframe}&apikey={ALPHA_VANTAGE_KEY}"
        res = requests.get(av_url, timeout=2.5).json()
        key = f"Time Series FX ({timeframe})"
        if key in res:
            raw_data = res[key]
            prices = [float(v['4. close']) for k, v in list(raw_data.items())[:35]][::-1]
            if len(prices) > 20:
                return calculate_from_prices(prices)
    except Exception as e:
        print("Alpha Vantage Fail:", e)

    # --- 4. YAHOO FINANCE (ALWAYS WORKS AS LAST RESORT) ---
    try:
        import yfinance as yf
        yf_symbol = coin.replace("/", "") + "=X"
        if "XAU" in coin: yf_symbol = "GC=F"

        df = yf.download(tickers=yf_symbol, period="1d", interval=timeframe, progress=False)
        if not df.empty:
            prices = df['Close'].values.flatten().tolist()
            prices = [float(x) for x in prices if not float('nan') == x][-35:]
            if len(prices) > 20:
                return calculate_from_prices(prices)
    except Exception as e:
        print("Yahoo Finance Fail:", e)

    return None

@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    data = get_market_data_safe(coin, timeframe)
    
    if data is None:
        return jsonify({
            "status": "error",
            "message": "All API endpoints and Fallbacks failed. Check connection."
        }), 500

    latest_price = data['price']
    latest_rsi = round(data['rsi'], 2)
    macd_line = data['macd_line']
    macd_signal = data['macd_signal']
    prev_macd_line = data['prev_macd_line']
    prev_macd_signal = data['prev_macd_signal']
    upper_band = data['upper_band']
    lower_band = data['lower_band']

    macd_bullish = (prev_macd_line <= prev_macd_signal) and (macd_line > macd_signal)
    macd_bearish = (prev_macd_line >= prev_macd_signal) and (macd_line < macd_signal)

    signal = "WAIT (NEUTRAL) 🟡"
    confidence = "LOW"
    action_type = "NO_ACTION"

    if (latest_rsi < 35) and macd_bullish:
        signal = "STRONG CALL 🟢"
        confidence = "HIGH"
        action_type = "CALL"
    elif (latest_rsi > 65) and macd_bearish:
        signal = "STRONG PUT 🔴"
        confidence = "HIGH"
        action_type = "PUT"
    elif latest_rsi < 40:
        signal = "WEAK CALL 🟢"
        confidence = "MEDIUM"
        action_type = "CALL"
    elif latest_rsi > 60:
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
            "macd_line": round(macd_line, 5)
        },
        "signal": signal,
        "action": action_type,
        "confidence": confidence
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
