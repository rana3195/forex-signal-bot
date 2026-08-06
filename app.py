import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Browser extensions aur TradingView/Quotex requests bypass karne ke liye

@app.route('/')
def home():
    return "Forex Strategy Backend Running Perfectly 🚀"

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json or {}
        
        # Extract Incoming Technical Data
        coin = data.get('coin', 'EUR/USD')
        timeframe = data.get('timeframe', '1m')
        price = float(data.get('price', 0.0))
        rsi = float(data.get('rsi', 50.0))
        atr = float(data.get('atr', 0.0005))
        
        buy_score = 0
        sell_score = 0
        reasons = []

        # ---------------------------------------------------------
        # 1. EMA Trend Filter (25 Points)
        # ---------------------------------------------------------
        ema_20 = float(data.get('ema_20', 0.0))
        ema_50 = float(data.get('ema_50', 0.0))
        
        if ema_20 > ema_50:
            buy_score += 25
            reasons.append("EMA Bullish Trend")
        elif ema_20 < ema_50:
            sell_score += 25
            reasons.append("EMA Bearish Trend")

        # ---------------------------------------------------------
        # 2. MACD Momentum (20 Points)
        # ---------------------------------------------------------
        macd_line = float(data.get('macd_line', 0.0))
        macd_signal = float(data.get('macd_signal', 0.0))
        
        if macd_line > macd_signal:
            buy_score += 20
            reasons.append("MACD Bullish Cross")
        else:
            sell_score += 20
            reasons.append("MACD Bearish Cross")

        # ---------------------------------------------------------
        # 3. RSI Direction & Boundary (15 Points)
        # ---------------------------------------------------------
        if rsi >= 55:
            buy_score += 15
            reasons.append("RSI Bullish (>55)")
        elif rsi <= 45:
            sell_score += 15
            reasons.append("RSI Bearish (<45)")

        # ---------------------------------------------------------
        # 4. Support & Resistance Rejection (15 Points)
        # ---------------------------------------------------------
        recent_low = float(data.get('recent_low', price))
        recent_high = float(data.get('recent_high', price))
        
        if price <= (recent_low * 1.0005):
            buy_score += 15
            reasons.append("Support Level Rejection")
        elif price >= (recent_high * 0.9995):
            sell_score += 15
            reasons.append("Resistance Level Rejection")

        # ---------------------------------------------------------
        # 5. Candlestick Confirmation (10 Points)
        # ---------------------------------------------------------
        if data.get('bullish_pattern'):
            buy_score += 10
            reasons.append("Bullish Price Action")
        elif data.get('bearish_pattern'):
            sell_score += 10
            reasons.append("Bearish Price Action")

        # ---------------------------------------------------------
        # 6. Directional Volume Spike Boost (15 Points - Fixed Logic)
        # ---------------------------------------------------------
        if data.get('vol_spike'):
            if buy_score > sell_score:
                buy_score += 15
                reasons.append("Bullish Volume Surge")
            elif sell_score > buy_score:
                sell_score += 15
                reasons.append("Bearish Volume Surge")

        # ---------------------------------------------------------
        # 7. ADX Strong Trend Booster (>18)
        # ---------------------------------------------------------
        adx = float(data.get('adx', 0.0))
        if adx > 18:
            if buy_score > sell_score:
                buy_score = min(buy_score + 5, 100)
            elif sell_score > buy_score:
                sell_score = min(sell_score + 5, 100)

        # ---------------------------------------------------------
        # HIGH ACCURACY DECISION ENGINE (Only Strong Signals)
        # ---------------------------------------------------------
        signal = "WAIT 🟡"
        action_type = "NO_ACTION"
        confidence = max(buy_score, sell_score)
        tp = price
        sl = price

        # Strictly filter out weak/medium signals (Cut-off >= 65%)
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
            "coin": coin,
            "timeframe": timeframe,
            "entry_price": round(price, 5),
            "signal": signal,
            "action": action_type,
            "confidence": f"{confidence}%",
            "take_profit": tp,
            "stop_loss": sl,
            "reason": " + ".join(reasons[:3]) if reasons else "Waiting for High Probability Confluence"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "signal": "WAIT 🟡",
            "action": "NO_ACTION",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
