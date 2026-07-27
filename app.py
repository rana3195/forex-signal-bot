from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

DEFAULT_API_KEY = "a592dba7321442efa229bee2b8a1cff8"
API_KEY = os.environ.get("TWELVE_DATA_API_KEY", DEFAULT_API_KEY)

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
# 📊 ADVANCED STRATEGY (RSI + MACD + BOLLINGER BANDS)
# ---------------------------------------------------------
@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    # 1. API URLs for Indicators
    rsi_url = f"https://api.twelvedata.com/rsi?symbol={coin}&interval={timeframe}&time_period=14&apikey={API_KEY}"
    macd_url = f"https://api.twelvedata.com/macd?symbol={coin}&interval={timeframe}&apikey={API_KEY}"
    bbands_url = f"https://api.twelvedata.com/bbands?symbol={coin}&interval={timeframe}&time_period=20&sd=2&apikey={API_KEY}"
    price_url = f"https://api.twelvedata.com/price?symbol={coin}&apikey={API_KEY}"

    try:
        # 2. Fetch Data from TwelveData
        rsi_res = requests.get(rsi_url).json()
        macd_res = requests.get(macd_url).json()
        bbands_res = requests.get(bbands_url).json()
        price_res = requests.get(price_url).json()

        # Check if all responses contain valid data
        if ("values" in rsi_res and "values" in macd_res and 
            "values" in bbands_res and "price" in price_res):
            
            # --- Extract Latest Indicators Values ---
            latest_price = float(price_res['price'])
            latest_rsi = float(rsi_res['values'][0]['rsi'])
            
            # MACD Values (Current & Previous for Crossover Detection)
            macd_line = float(macd_res['values'][0]['macd'])
            macd_signal = float(macd_res['values'][0]['macd_signal'])
            prev_macd_line = float(macd_res['values'][1]['macd'])
            prev_macd_signal = float(macd_res['values'][1]['macd_signal'])
            
            # Bollinger Bands Values
            upper_band = float(bbands_res['values'][0]['upper_band'])
            lower_band = float(bbands_res['values'][0]['lower_band'])
            middle_band = float(bbands_res['values'][0]['middle_band'])

            # --- STRATEGY CONDITIONS ---
            
            # 1. MACD Bullish Crossover: MACD line bottom se Signal line ko cross karke upar jaye
            macd_bullish = (prev_macd_line <= prev_macd_signal) and (macd_line > macd_signal)
            
            # 2. MACD Bearish Crossover: MACD line top se Signal line ko cross karke neeche aaye
            macd_bearish = (prev_macd_line >= prev_macd_signal) and (macd_line < macd_signal)
            
            # 3. Bollinger Rejections
            price_at_lower_band = latest_price <= lower_band
            price_at_upper_band = latest_price >= upper_band

            signal = "WAIT (NEUTRAL) 🟡"
            confidence = "LOW"
            action_type = "NO_ACTION"

            # --- CALL (BUY) SIGNAL LOGIC ---
            # Condition: RSI < 30 + MACD Bullish Crossover + Lower BBand Rejection/Bounce
            if (latest_rsi < 30) and macd_bullish and price_at_lower_band:
                signal = "STRONG CALL 🟢 (RSI + MACD + BB Bounce)"
                confidence = "HIGH"
                action_type = "CALL"

            # --- PUT (SELL) SIGNAL LOGIC ---
            # Condition: RSI > 70 + MACD Bearish Crossover + Upper BBand Rejection
            elif (latest_rsi > 70) and macd_bearish and price_at_upper_band:
                signal = "STRONG PUT 🔴 (RSI + MACD + BB Rejection)"
                confidence = "HIGH"
                action_type = "PUT"
                
            # Moderate Signals (Agar 2 confirmations milein)
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
            
        else:
            return jsonify({
                "status": "error",
                "message": "Indicators ka data load nahi ho saka. TwelveData API limits check karein.",
                "raw_errors": {
                    "rsi": rsi_res.get("message"),
                    "macd": macd_res.get("message"),
                    "bbands": bbands_res.get("message")
                }
            }), 400

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
