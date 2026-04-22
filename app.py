import os
import base64
from datetime import datetime

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
SHORTCODE = os.getenv("BUSINESS_SHORTCODE", "4567769")
PASSKEY = os.getenv("PASSKEY")
CALLBACK_URL = os.getenv("CALLBACK_URL")

payments = {}

def format_phone(phone: str) -> str:
    phone = str(phone).strip().replace(" ", "")
    if phone.startswith("0"):
        return "254" + phone[1:]
    if phone.startswith("+254"):
        return phone[1:]
    return phone

def get_access_token():
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        raise ValueError("Missing CONSUMER_KEY or CONSUMER_SECRET")

    url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=30)
    response.raise_for_status()
    return response.json().get("access_token")

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "Hopestone backend running"
    })

@app.route("/stkpush", methods=["POST"])
def stk_push():
    try:
        data = request.get_json(force=True)

        phone = format_phone(data.get("phone", ""))
        amount = int(data.get("amount", 0))
        order_id = str(data.get("order_id", "")).strip()

        if not phone or amount <= 0 or not order_id:
            return jsonify({
                "success": False,
                "message": "phone, amount and order_id are required"
            }), 400

        if not PASSKEY or not CALLBACK_URL:
            return jsonify({
                "success": False,
                "message": "Missing PASSKEY or CALLBACK_URL"
            }), 500

        access_token = get_access_token()
        if not access_token:
            return jsonify({
                "success": False,
                "message": "Failed to get access token"
            }), 500

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            (SHORTCODE + PASSKEY + timestamp).encode("utf-8")
        ).decode("utf-8")

        url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "BusinessShortCode": SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone,
            "PartyB": SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": CALLBACK_URL,
            "AccountReference": "Hopestone Mart",
            "TransactionDesc": "Hopestone Mart Order Payment"
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        result = response.json()

        checkout_id = result.get("CheckoutRequestID")

        payments[order_id] = {
            "order_id": order_id,
            "phone": phone,
            "amount": amount,
            "status": "PENDING",
            "checkout_request_id": checkout_id,
            "raw": result
        }

        return jsonify({
            "success": True,
            "message": "STK push sent",
            "order_id": order_id,
            "checkout_request_id": checkout_id,
            "mpesa_response": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route("/callback", methods=["POST"])
def callback():
    try:
        data = request.get_json(force=True)

        stk = data.get("Body", {}).get("stkCallback", {})
        checkout_id = stk.get("CheckoutRequestID")
        result_code = stk.get("ResultCode")
        result_desc = stk.get("ResultDesc")

        amount = None
        mpesa_receipt = None
        phone = None

        for item in stk.get("CallbackMetadata", {}).get("Item", []):
            name = item.get("Name")
            value = item.get("Value")
            if name == "Amount":
                amount = value
            elif name == "MpesaReceiptNumber":
                mpesa_receipt = value
            elif name == "PhoneNumber":
                phone = value

        for order_id, record in payments.items():
            if record.get("checkout_request_id") == checkout_id:
                record["status"] = "PAID" if result_code == 0 else "FAILED"
                record["result_code"] = result_code
                record["result_desc"] = result_desc
                record["mpesa_receipt"] = mpesa_receipt
                record["paid_amount"] = amount
                record["paid_phone"] = phone
                record["callback"] = data
                break

        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })

    except Exception as e:
        return jsonify({
            "ResultCode": 1,
            "ResultDesc": str(e)
        }), 500

@app.route("/payment-status/<order_id>", methods=["GET"])
def payment_status(order_id):
    record = payments.get(order_id)

    if not record:
        return jsonify({
            "success": False,
            "message": "Order not found"
        }), 404

    return jsonify({
        "success": True,
        "payment": record
    })

if __name__ == "__main__":
    app.run(debug=True)
