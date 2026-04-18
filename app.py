from flask import Flask, request, jsonify
import requests
import base64
from datetime import datetime

app = Flask(__name__)

# 🔐 YOUR MPESA PRODUCTION DETAILS (PASTE YOURS HERE)
CONSUMER_KEY = "3VYqMLfH4oh1XE5EBX63nexiLdJHhncfkaQ5LSf66hr5Fp6F"
CONSUMER_SECRET = "baSTWNV1AZa58tBAfvfbNiW8sg9AA8bgBanX1mMUl1y3M8JzY3Qog6Q2317fMXGu"
SHORTCODE = "4567573"
PASSKEY = "07e7bcf59e6221694990890b85cec2933a18f385626143c07e618dd9918329ec"

# 🔗 Replace after deploying on Render
CALLBACK_URL = "https://your-backend.onrender.com/callback"

# Temporary storage (for now)
payments = {}

# Format phone number to 254 format
def format_phone(phone: str) -> str:
    phone = str(phone).strip().replace(" ", "")
    if phone.startswith("0"):
        return "254" + phone[1:]
    if phone.startswith("+254"):
        return phone[1:]
    return phone

# Get access token
def get_access_token():
    url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]

# Test route
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Hopestone backend running"})

# STK Push route
@app.route("/stkpush", methods=["POST"])
def stk_push():
    data = request.get_json(force=True)

    phone = format_phone(data.get("phone", ""))
    amount = int(data.get("amount", 0))
    order_id = str(data.get("order_id", ""))

    if not phone or amount <= 0 or not order_id:
        return jsonify({
            "success": False,
            "message": "phone, amount and order_id are required"
        }), 400

    access_token = get_access_token()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode((SHORTCODE + PASSKEY + timestamp).encode()).decode("utf-8")

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

    # Save payment
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

# Callback from Safaricom
@app.route("/callback", methods=["POST"])
def callback():
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

    # Update payment status
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

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

# Check payment status
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

# Run app
if __name__ == "__main__":
    app.run(debug=True)
