from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
# Extension ko server se dynamic data exchange ki ijazat dene ke liye
CORS(app)

# =========================================================
# 🔑 APNI TWELVE DATA API KEY NEECHE QUOTES (' ') MEIN DALEN
# =========================================================
DEFAULT_API_KEY = "a592dba7321442efa229bee2b8a1cff8"

# Koyeb environment variable check karega, agar wahan na ho toh DEFAULT_API_KEY use karega
API_KEY = os.environ.get("TWELVE_DATA_API_KEY", DEFAULT_API_KEY)

@app.route('/')
def home():
    return "Forex Signal Server is Running Perfectly! 🚀"

@app.route('/analyze', methods=['GET'])
def analyze():
    # Chrome extension se coin aur timeframe receive karna
    coin = request.args.get('coin', 'EUR/USD')
    timeframe = request.args.get('timeframe', '1min')
    
    # Twelve Data API URL for RSI (14)
    rsi_url = f"https://api.twelvedata.com/rsi?symbol={coin}&interval={timeframe}&time_period=14&apikey={API_KEY}"
    
    try:
        response = requests.get(rsi_url)
        res_data = response.json()
        
        # Checking if valid RSI values returned
        if "values" in res_data and len(res_data["values"]) > 0:
            latest_rsi = float(res_data['values'][0]['rsi'])
            
            # Pure Signal Logic based on RSI
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
                "message": "Data fetch nahi ho saka. Symbol/API key check karein.",
                "raw": res_data
            }), 400
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # Koyeb aur Local dono par chalne ke liye port configuration
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
