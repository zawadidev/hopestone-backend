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
CALLBACK_URL = os.getenv("CALLBACK_URL", "https://hopestone-backend.onrender.com/callback")

payments = {}


def format_phone(phone: str) -> str:
    phone = str(phone).strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        return "254" + phone[1:]
    if phone.startswith("7") and len(phone) == 9:
        return "254" + phone
    if phone.startswith("1") and len(phone) == 9:
        return "254" + phone
    return phone


def get_access_token():
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        raise ValueError("Missing CONSUMER_KEY or CONSUMER_SECRET")

    url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(
        url,
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=30
    )
    response.raise_for_status()
    return response.json().get("access_token")


def initiate_stk(phone: str, amount, order_id: str):
    if not PASSKEY:
        raise ValueError("Missing PASSKEY")

    phone = format_phone(phone)

    if not phone:
        raise ValueError("Phone number is required")

    try:
        amount = int(float(amount))
    except Exception:
        raise ValueError("Amount must be a valid number")

    if amount < 1:
        raise ValueError("Amount must be at least 1")

    access_token = get_access_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password_string = f"{SHORTCODE}{PASSKEY}{timestamp}"
    password = base64.b64encode(password_string.encode()).decode()

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
        "AccountReference": order_id,
        "TransactionDesc": f"Payment for {order_id}"
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    result = response.json()

    payments[order_id] = {
        "order_id": order_id,
        "phone": phone,
        "requested_amount": amount,
        "merchant_request_id": result.get("MerchantRequestID"),
        "checkout_request_id": result.get("CheckoutRequestID"),
        "status": "PENDING",
        "result_code": None,
        "result_desc": result.get("ResponseDescription"),
        "mpesa_receipt": None,
        "paid_amount": None,
        "paid_phone": None
    }

    return result


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "Hopestone backend running"
    })


@app.route("/stkpush", methods=["POST"])
def stk_push():
    try:
        data = request.get_json(force=True) or {}
        phone = data.get("phone", "")
        amount = data.get("amount", 0)
        order_id = str(data.get("order_id", "")).strip()

        if not order_id:
            order_id = f"ORDER{datetime.now().strftime('%Y%m%d%H%M%S')}"

        result = initiate_stk(phone, amount, order_id)

        return jsonify({
            "success": True,
            "message": "STK push initiated",
            "order_id": order_id,
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/pay", methods=["GET"])
def pay():
    try:
        phone = request.args.get("phone", "").strip()
        amount = request.args.get("amount", "").strip()
        order_id = request.args.get("order_id", "").strip()

        if not order_id:
            order_id = f"ORDER{datetime.now().strftime('%Y%m%d%H%M%S')}"

        result = initiate_stk(phone, amount, order_id)

        return jsonify({
            "success": True,
            "message": "STK push initiated",
            "order_id": order_id,
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/callback", methods=["POST"])
def callback():
    try:
        payload = request.get_json(force=True) or {}

        body = payload.get("Body", {})
        stk = body.get("stkCallback", {})

        merchant_request_id = stk.get("MerchantRequestID")
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
                record["merchant_request_id"] = merchant_request_id
                record["status"] = "PAID" if result_code == 0 else "FAILED"
                record["result_code"] = result_code
                record["result_desc"] = result_desc
                record["paid_amount"] = amount
                record["mpesa_receipt"] = mpesa_receipt
                record["paid_phone"] = phone
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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
