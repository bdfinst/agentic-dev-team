from auth import require_token
from clients.payments import charge
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify(ok=True)


@app.route("/orders/<int:order_id>/pay", methods=["POST"])
@require_token
def pay(order_id):
    body = request.get_json()
    result = charge(order_id, body["amount_cents"])
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
