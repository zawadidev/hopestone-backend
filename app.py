import os
import base64
from datetime import datetime

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
# Uses your existing Render environment variables
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
PASSKEY = os.getenv("PASSKEY")
CALLBACK_URL = os.getenv("CALLBACK_URL", "https://hopestone-backend.onrender.com/callback")

# Fixed working setup
SHORTCODE = "4567769"
TILL_NUMBER = "5402532"

payments = {}


def get_access_token():
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        raise ValueError("Missing CONSUMER_KEY or CONSUMER_SECRET in Render environment")

    url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=30)
    response.raise_for_status()
    token = response.json().get("access_token")

    if not token:
        raise ValueError("Failed to get access token")

    return token


def format_phone(phone):
    phone = str(phone).strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        return "254" + phone[1:]
    if phone.startswith("7") and len(phone) == 9:
        return "254" + phone
    if phone.startswith("1") and len(phone) == 9:
        return "254" + phone
    return phone


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Hopestone backend running",
        "success": True
    })


@app.route("/pay", methods=["GET"])
def pay():
    try:
        phone = request.args.get("phone")
        amount = request.args.get("amount")
        order_id = request.args.get("order_id")

        if not phone or not amount or not order_id:
            return jsonify({
                "success": False,
                "message": "phone, amount and order_id are required"
            }), 400

        if not PASSKEY:
            return jsonify({
                "success": False,
                "message": "Missing PASSKEY in Render environment"
            }), 500

        phone = format_phone(phone)
        amount = int(amount)

        access_token = get_access_token()

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
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
            "PartyB": TILL_NUMBER,
            "PhoneNumber": phone,
            "CallBackURL": CALLBACK_URL,
            "AccountReference": order_id,
            "TransactionDesc": "Payment"
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        payments[order_id] = {
            "order_id": order_id,
            "status": "PENDING",
            "phone": phone,
            "amount": amount,
            "checkout_request_id": result.get("CheckoutRequestID"),
            "merchant_request_id": result.get("MerchantRequestID")
        }

        return jsonify({
            "success": True,
            "message": "STK Push sent",
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/callback", methods=["POST"])
def callback():
    data = request.json

    try:
        stk = data["Body"]["stkCallback"]
        result_code = stk.get("ResultCode")
        checkout_request_id = stk.get("CheckoutRequestID")
        result_desc = stk.get("ResultDesc")

        mpesa_receipt = None
        paid_amount = None
        paid_phone = None

        items = stk.get("CallbackMetadata", {}).get("Item", [])
        for item in items:
            name = item.get("Name")
            value = item.get("Value")
            if name == "MpesaReceiptNumber":
                mpesa_receipt = value
            elif name == "Amount":
                paid_amount = value
            elif name == "PhoneNumber":
                paid_phone = value

        for order_id, record in payments.items():
            if record.get("checkout_request_id") == checkout_request_id:
                if result_code == 0:
                    record["status"] = "PAID"
                else:
                    record["status"] = "FAILED"

                record["result_code"] = result_code
                record["result_desc"] = result_desc
                record["mpesa_receipt"] = mpesa_receipt
                record["paid_amount"] = paid_amount
                record["paid_phone"] = paid_phone
                break

    except Exception as e:
        print("Callback error:", e)

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
