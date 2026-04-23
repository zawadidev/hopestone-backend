import os
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔑 YOUR SAFARICOM DETAILS (PUT YOUR REAL VALUES)
CONSUMER_KEY = "KmPlf9xIKBpZShAF9pBNo7a9YQRAxaVf0yje6Hi0RdjGyM6H"
CONSUMER_SECRET = "ZryQKUUnpjCJYdA0xh7xC7nZQDIUYrlrjjcBmOProRSti6HymmGXEjXixbL2BjHG"
SHORTCODE = "4567769"
PASSKEY = "b4dca8192ffa29e2c154b757256c120eddca0bd824b88efd6b8098958f459c91"
CALLBACK_URL = "https://hopestone-backend.onrender.com/callback"

payments = {}

# 🔐 GET ACCESS TOKEN
def get_access_token():
    url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    return response.json().get("access_token")


# 🚀 STK PUSH
@app.route("/pay", methods=["GET"])
def pay():
    phone = request.args.get("phone")
    amount = int(request.args.get("amount"))
    order_id = request.args.get("order_id")

    access_token = get_access_token()

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode((SHORTCODE + PASSKEY + timestamp).encode()).decode()

    url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerBuyGoodsOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": "5402532",  # YOUR TILL NUMBER
        "PhoneNumber": phone,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": "Payment"
    }

    response = requests.post(url, json=payload, headers=headers)
    result = response.json()

    payments[order_id] = {
        "status": "PENDING",
        "phone": phone,
        "amount": amount
    }

    return jsonify({
        "success": True,
        "message": "STK Push sent",
        "data": result
    })


# 🔔 CALLBACK FROM SAFARICOM
@app.route("/callback", methods=["POST"])
def callback():
    data = request.json

    try:
        stk = data["Body"]["stkCallback"]
        result_code = stk["ResultCode"]

        items = stk.get("CallbackMetadata", {}).get("Item", [])

        order_id = None

        for item in items:
            if item.get("Name") == "AccountReference":
                order_id = item.get("Value")

        if order_id and order_id in payments:
            if result_code == 0:
                payments[order_id]["status"] = "PAID"
            else:
                payments[order_id]["status"] = "FAILED"

    except Exception as e:
        print("Callback error:", e)

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


# 📊 CHECK PAYMENT STATUS
@app.route("/payment-status/<order_id>", methods=["GET"])
def payment_status(order_id):
    if order_id in payments:
        return jsonify({
            "success": True,
            "data": payments[order_id]
        })
    else:
        return jsonify({
            "success": False,
            "message": "Order not found"
        }), 404


# 🟢 HOME
@app.route("/")
def home():
    return jsonify({
        "message": "Hopestone backend running",
        "success": True
    })


if __name__ == "__main__":
    app.run()
