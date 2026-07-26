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
    return "Forex Signal Server is Running Perfectly! 🚀"

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
# 📊 HIGH-ACCURACY STRATEGY (RSI + 200 EMA TREND FILTER)
# ---------------------------------------------------------
@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    # 1. API Endpoints (RSI Period 14 & EMA Period 200)
    rsi_url = f"https://api.twelvedata.com/rsi?symbol={coin}&interval={timeframe}&time_period=14&apikey={API_KEY}"
    ema_url = f"https://api.twelvedata.com/ema?symbol={coin}&interval={timeframe}&time_period=200&apikey={API_KEY}"
    price_url = f"https://api.twelvedata.com/price?symbol={coin}&apikey={API_KEY}"

    try:
        # Fetching Market Data
        rsi_res = requests.get(rsi_url).json()
        ema_res = requests.get(ema_url).json()
        price_res = requests.get(price_url).json()

        if "values" in rsi_res and "values" in ema_res and "price" in price_res:
            latest_rsi = float(rsi_res['values'][0]['rsi'])
            latest_ema = float(ema_res['values'][0]['ema'])
            current_price = float(price_res['price'])

            # Strategy Logic Parameters
            # Gap ko kam karke: 40 Oversold, 60 Overbought banaya gaya hai
            is_uptrend = current_price > latest_ema
            is_downtrend = current_price < latest_ema

            signal = "WAIT (NEUTRAL) 🟡"
            confidence = "LOW"
            trend_direction = "UPTREND 📈" if is_uptrend else "DOWNTREND 📉"

            # Strong Low-Risk Signal Logic
            if latest_rsi < 40 and is_uptrend:
                signal = "STRONG BUY 🟢 (High Accuracy)"
                confidence = "HIGH"
            elif latest_rsi > 60 and is_downtrend:
                signal = "STRONG SELL 🔴 (High Accuracy)"
                confidence = "HIGH"
            elif latest_rsi < 40 and is_downtrend:
                signal = "WEAK BUY ⚠️ (Counter-Trend Risk)"
                confidence = "MEDIUM"
            elif latest_rsi > 60 and is_uptrend:
                signal = "WEAK SELL ⚠️ (Counter-Trend Risk)"
                confidence = "MEDIUM"
            else:
                signal = "WAIT (NO CLEAR ENTRY) 🟡"
                confidence = "LOW"

            return jsonify({
                "status": "success",
                "coin": coin,
                "timeframe": timeframe,
                "current_price": round(current_price, 5),
                "rsi_value": round(latest_rsi, 2),
                "ema_200": round(latest_ema, 5),
                "market_trend": trend_direction,
                "signal": signal,
                "signal_confidence": confidence
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Data fetch nahi ho saka. TwelveData API limits ya symbol check karein.",
                "rsi_raw": rsi_res,
                "ema_raw": ema_res
            }), 400

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
        
