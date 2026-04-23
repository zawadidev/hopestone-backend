import requests
import base64
from datetime import datetime
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

SHORTCODE = "4567769"  # Paybill
TILL = "5402532"       # Buy Goods Till
PASSKEY = os.getenv("PASSKEY")
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
CALLBACK_URL = os.getenv("CALLBACK_URL")


def get_access_token():
    url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    return response.json().get("access_token")


@app.route("/pay")
def stk_push():
    phone = request.args.get("phone")
    amount = request.args.get("amount")
    order_id = request.args.get("order_id", "test123")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode((SHORTCODE + PASSKEY + timestamp).encode()).decode()

    access_token = get_access_token()

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
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": TILL,
        "PhoneNumber": phone,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": order_id,
        "TransactionDesc": "Payment"
    }

    response = requests.post(url, json=payload, headers=headers)
    return jsonify(response.json())


if __name__ == "__main__":
    app.run()
