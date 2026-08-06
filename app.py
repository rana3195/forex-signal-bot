import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------
# TWELVE DATA API KEYS (BOTH ARE WORKING 🟢)
# ---------------------------------------------------------
TWELVE_DATA_KEY_1 = "a592dba7321442efa229bee2b8a1cff8"
TWELVE_DATA_KEY_2 = "5f98e9f032684d27b8b266656bfcadac"

def fetch_market_data(symbol, api_key, source_name):
    """ Helper function to fetch live data from Twelve Data """
    try:
        # Convert symbol format just in case (e.g., OANDA:EUR_USD -> EUR/USD)
        clean_symbol = symbol.replace("OANDA:", "").replace("_", "/")
        url = f"https://api.twelvedata.com/quote?symbol={clean_symbol}&apikey={api_key}"
        res = requests.get(url, timeout=3)
        
        if res.status_code == 200:
            data = res.json()
            # Strict check if data actually exists and not an API limit message
            if 'close' in data and float(data.get('close', 0)) > 0:
                return {
                    "price": float(data['close']),
                    "high": float(data['high']),
                    "low": float(data['low']),
                    "source": source_name
                }
    except Exception as e:
        print(f"Error fetching from {source_name}: {e}")
    return None

@app.route('/')
def home():
    return "Dual Twelve Data Signal Engine Active 🚀"

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        payload = request.json or {}
        symbol = payload.get('coin', 'EUR/USD')
        timeframe = payload.get('timeframe', '1m')

        # ---------------------------------------------------------
        # 1. DUAL TWELVE DATA FAILOVER SYSTEM
        # ---------------------------------------------------------
        # Attempt 1: Using the First Twelve Data Key
        market_data = fetch_market_data(symbol, TWELVE_DATA_KEY_1, "Twelve Data (Key 1) 🟢")
        
        # Attempt 2: Fallback to the Second Twelve Data Key if Key 1 limits out
        if not market_data:
            market_data = fetch_market_data(symbol, TWELVE_DATA_KEY_2, "Twelve Data (Key 2) 🔵")

        # IF BOTH KEYS FAIL -> ABSOLUTE ERROR RESPONSE (NO FAKE PAYLOAD)
        if not market_data:
            return jsonify({
                "status": "error",
                "signal": "ERROR ❌",
                "action": "NO_ACTION",
                "message": "Both Twelve Data API Keys hit their rate limits. Trade blocked for safety!"
            }), 429

        # Extract live values from the active key
        price = market_data['price']
        recent_high = market_data['high']
        recent_low = market_data['low']
        source = market_data['source']

        # Extract strategy indicators sent by your extension
        rsi = float(payload.get('rsi', 50.0))
        atr = float(payload.get('atr', 0.0005))
        ema_20 = float(payload.get('ema_20', 0.0))
        ema_50 = float(payload.get('ema_50', 0.0))
        macd_line = float(payload.get('macd_line', 0.0))
        macd_signal = float(payload.get('macd_signal', 0.0))
        
        buy_score = 0
        sell_score = 0
        reasons = []

        # ---------------------------------------------------------
        # 2. CONFLUENCE STRATEGY EVALUATION
        # ---------------------------------------------------------
        # EMA Trend (25 Points)
        if ema_20 > ema_50:
            buy_score += 25
            reasons.append("EMA Bullish Trend")
        elif ema_20 < ema_50:
            sell_score += 25
            reasons.append("EMA Bearish Trend")

        # MACD Crossover (20 Points)
        if macd_line > macd_signal:
            buy_score += 20
            reasons.append("MACD Bullish Cross")
        else:
            sell_score += 20
            reasons.append("MACD Bearish Cross")

        # RSI Momentum (15 Points)
        if rsi >= 55:
            buy_score += 15
            reasons.append("RSI Momentum (>55)")
        elif rsi <= 45:
            sell_score += 15
            reasons.append("RSI Bearish (<45)")

        # Real-Time Support / Resistance Bounce (15 Points)
        if price <= (recent_low * 1.0005):
            buy_score += 15
            reasons.append("At Real-Time Support")
        elif price >= (recent_high * 0.9995):
            sell_score += 15
            reasons.append("At Real-Time Resistance")

        # Candlestick Price Action Patterns (10 Points)
        if payload.get('bullish_pattern'):
            buy_score += 10
            reasons.append("Bullish Price Action")
        elif payload.get('bearish_pattern'):
            sell_score += 10
            reasons.append("Bearish Price Action")

        # Directional Volume Spike Boost (15 Points)
        if payload.get('vol_spike'):
            if buy_score > sell_score:
                buy_score += 15
                reasons.append("Bullish Volume Surge")
            elif sell_score > buy_score:
                sell_score += 15
                reasons.append("Bearish Volume Surge")

        # ---------------------------------------------------------
        # 3. HIGH PRECISION DECISION ENGINE (Cut-off >= 65%)
        # ---------------------------------------------------------
        signal = "WAIT 🟡"
        action_type = "NO_ACTION"
        confidence = max(buy_score, sell_score)
        tp = price
        sl = price

        if buy_score >= 65 and buy_score > sell_score:
            signal = "STRONG BUY 🟢"
            action_type = "CALL"
            sl = round(price - (atr * 1.5), 5)
            tp = round(price + (atr * 2.5), 5)

        elif sell_score >= 65 and sell_score > buy_score:
            signal = "STRONG SELL 🔴"
            action_type = "PUT"
            sl = round(price + (atr * 1.5), 5)
            tp = round(price - (atr * 2.5), 5)

        return jsonify({
            "status": "success",
            "data_source": source,
            "coin": symbol,
            "timeframe": timeframe,
            "entry_price": round(price, 5),
            "signal": signal,
            "action": action_type,
            "confidence": f"{confidence}%",
            "take_profit": tp,
            "stop_loss": sl,
            "reason": " + ".join(reasons[:3]) if reasons else "Waiting for High Confluence"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "signal": "ERROR ❌",
            "action": "NO_ACTION",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
