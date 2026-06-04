from flask import Blueprint, jsonify, request
import requests

kaspi_pos_bp = Blueprint("kaspi_pos", __name__)

POS_IP = "10.22.108.105"


@kaspi_pos_bp.route("/kaspi/start-payment", methods=["POST"])
def start_payment():

    data = request.get_json()

    amount = int(data.get("amount", 0))

    try:

        r = requests.get(
            f"http://{POS_IP}:8080/v2/payment",
            params={
                "amount": amount
            },
            timeout=10
        )

        result = r.json()

        if result.get("statusCode") != 0:

            return jsonify({
                "success": False,
                "error": result
            })

        return jsonify({
            "success": True,
            "processId":
                result["data"]["processId"]
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        })
        
@kaspi_pos_bp.route("/kaspi/status/<process_id>")
def payment_status(process_id):

    try:
        r = requests.get(
            f"http://{POS_IP}:8080/v2/status",
            params={"processId": process_id},
            timeout=10
        )

        result = r.json()
        data = result.get("data", {})

        return jsonify({
            "status": data.get("status"),
            "subStatus": data.get("subStatus"),
            "message": data.get("message"),
            "transactionId": data.get("transactionId"),
            "method": data.get("chequeInfo", {}).get("method"),
            "raw": result
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })