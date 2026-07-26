from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

DEFAULT_API_KEY = "a592dba7321442efa229bee2b8a1cff8"
API_KEY = os.environ.get("TWELVE_DATA_API_KEY", DEFAULT_API_KEY)

# ===========# ===================================================
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
# 📊 RSI SIGNAL ANALYZER ROUTE
# ---------------------------------------------------------
@app.route('/analyze', methods=['GET'])
def analyze():
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    rsi_url = f"https://api.twelvedata.com/rsi?symbol={coin}&interval={timeframe}&time_period=14&apikey={API_KEY}"
    
    try:
        response = requests.get(rsi_url)
        res_data = response.json()
        
        if "values" in res_data and len(res_data["values"]) > 0:
            latest_rsi = float(res_data['values'][0]['rsi'])
            
            if latest_rsi < 30:
                signal = "STRONG BUY 🟢"
            elif latest_rsi > 70:
                signal = "STRONG SELL 🔴"
            else:
                signal = "WAIT (NEUTRAL) 🟡"
                
            return jsonify({
                "status": "success",
                "coin": coin,
                "timeframe": timeframe,
                "rsi_value": round(latest_rsi, 2),
                "signal": signal
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Data fetch nahi ho saka.",
                "raw": res_data
            }), 400
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
