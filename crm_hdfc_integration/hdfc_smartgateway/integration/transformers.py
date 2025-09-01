from crm_hdfc_integration import utils

SYSTEM_STATUS_MAP = {
    "NEW": "New",
    "STARTED": "Started",
    "PENDING": "Pending",
    "SUCCESS": "Success",
    "CARD_PAYMENT_FAILED": "Card Payment Failed",
    "FAILED": "Failed",
    "CANCELLED": "Cancelled",
    "AUTO_REFUNDED": "Auto Refunded",
}

SYSTEM_PAYMENT_METHOD_MAP = {
    "NULL": "",
    "CARD": "Card",
    "NET_BANKING": "Netbanking",
    "WALLET": "Wallets",
    "UPI": "UPI",
}

HDFC_STATUS_ID_MAP = {
    10: SYSTEM_STATUS_MAP["NEW"],
    23: SYSTEM_STATUS_MAP["PENDING"],
    21: SYSTEM_STATUS_MAP["SUCCESS"],
    25: SYSTEM_STATUS_MAP["PENDING"],  # Authorized
    22: SYSTEM_STATUS_MAP["CARD_PAYMENT_FAILED"],  # Juspay Declined
    26: SYSTEM_STATUS_MAP["FAILED"],  # Authentication Failed
    27: SYSTEM_STATUS_MAP["FAILED"],  # Authorization Failed
    28: SYSTEM_STATUS_MAP["PENDING"],  # Authorizing
    31: SYSTEM_STATUS_MAP["CANCELLED"],  # Voided
    32: SYSTEM_STATUS_MAP["PENDING"],  # Void Initiated
    33: SYSTEM_STATUS_MAP[
        "PENDING"
    ],  # HDFC uses 33 for both VOID_FAILED and CAPTURE_INITIATED
    20: SYSTEM_STATUS_MAP["STARTED"],
    36: SYSTEM_STATUS_MAP["AUTO_REFUNDED"],
    34: SYSTEM_STATUS_MAP["FAILED"],  # Captured Failed
}

HDFC_STATUS_MAP = {
    "NEW": SYSTEM_STATUS_MAP["NEW"],
    "PENDING_VBV": SYSTEM_STATUS_MAP["PENDING"],
    "CHARGED": SYSTEM_STATUS_MAP["SUCCESS"],
    "AUTHORIZED": SYSTEM_STATUS_MAP["PENDING"],  # Authorized
    "JUSPAY_DECLINED": SYSTEM_STATUS_MAP["CARD_PAYMENT_FAILED"],  # Juspay Declined
    "AUTHENTICATION_FAILED": SYSTEM_STATUS_MAP["FAILED"],  # Authentication Failed
    "AUTHORIZATION_FAILED": SYSTEM_STATUS_MAP["FAILED"],  # Authorization Failed
    "AUTHORIZING": SYSTEM_STATUS_MAP["PENDING"],  # Authorizing
    "VOIDED": SYSTEM_STATUS_MAP["CANCELLED"],  # Voided
    "VOID_INITIATED": SYSTEM_STATUS_MAP["PENDING"],  # Void Initiated
    "VOID_FAILED": SYSTEM_STATUS_MAP[
        "PENDING"
    ],  # HDFC uses 33 for both VOID_FAILED and CAPTURE_INITIATED
    "STARTED": SYSTEM_STATUS_MAP["STARTED"],
    "AUTO_REFUNDED": SYSTEM_STATUS_MAP["AUTO_REFUNDED"],
    "CAPTURE_INITIATED": SYSTEM_STATUS_MAP["PENDING"],
    "CAPTURE_FAILED": SYSTEM_STATUS_MAP["FAILED"],  # Captured Failed
}

HDFC_PAYMENT_METHOD_MAP = {
    "CARD": SYSTEM_PAYMENT_METHOD_MAP["CARD"],
    "NB": SYSTEM_PAYMENT_METHOD_MAP["NET_BANKING"],
    "WALLET": SYSTEM_PAYMENT_METHOD_MAP["WALLET"],
    "UPI": SYSTEM_PAYMENT_METHOD_MAP["UPI"],
}


def parse_session_res(session_res):
    return {
        "sdk_payload": session_res.sdk_payload,
        "payment_link": session_res.payment_links.web,
        "payment_link_expiry": session_res.payment_links.expiry,
        "order_id": session_res.order_id,
        "status": HDFC_STATUS_MAP[session_res.status],
    }


def parse_order_status_res(order_status_res):
    user_defined_values = {
        "udf1": order_status_res["udf1"],
        "udf2": order_status_res["udf2"],
        "udf3": order_status_res["udf3"],
        "udf4": order_status_res["udf4"],
        "udf5": order_status_res["udf5"],
        "udf6": order_status_res["udf6"],
        "udf7": order_status_res["udf7"],
        "udf8": order_status_res["udf8"],
        "udf9": order_status_res["udf9"],
        "udf10": order_status_res["udf10"],
    }

    txn_details = order_status_res.get("txn_detail") or {}

    order_status_data = {
        "status": HDFC_STATUS_ID_MAP[order_status_res["status_id"]],
        "amount": order_status_res["amount"],
        "user_defined_values": user_defined_values,
        "payment_method": HDFC_PAYMENT_METHOD_MAP[
            order_status_res["payment_method_type"]
        ],
        "payment_service": order_status_res["payment_method"],
        "refunded": order_status_res["refunded"],
        "amount_refunded": order_status_res["amount_refunded"],
        "effective_amount": order_status_res["effective_amount"],
        "response_code": order_status_res["resp_code"],
        "response_message": order_status_res["resp_message"],
        "bank_error_code": order_status_res["bank_error_code"],
        "bank_error_message": order_status_res["bank_error_message"],
        "txn_id": txn_details.get("txn_id"),
        "txn_uuid": txn_details.get("txn_uuid"),
        "txn_status": txn_details.get("status"),
        "txn_date": utils.parse_utc_datetime(txn_details.get("created")),
        "txn_currency": txn_details.get("currency"),
        "txn_net_amount": txn_details.get("net_amount"),
        "txn_supercharge_amount": txn_details.get("surcharge_amount"),
        "txn_tax_amount": txn_details.get("tax_amount"),
        "txn_amount": txn_details.get("txn_amount"),
        "txn_offer_deduction_amount": txn_details.get("offer_deduction_amount"),
        "txn_error_code": txn_details.get("error_code"),
        "txn_error_message": txn_details.get("error_message"),
        "express_checkout": txn_details.get("express_checkout"),
        "gateway": txn_details.get("gateway"),
        "txn_amount_breakup": [
            {
                "idx": amnt_break.get("sno"),
                "breakup_name": amnt_break.get("name"),
                "value": amnt_break.get("value"),
                "method": amnt_break.get("method"),
                "description": amnt_break.get("desc"),
            }
            for amnt_break in txn_details.get("txn_amount_breakup") or []
        ],
        "gateway_id": order_status_res["gateway_id"],
        "gateway_reference_id": order_status_res["gateway_reference_id"],
    }

    if order_status_res.get("card"):
        card_res = order_status_res["card"]
        order_status_data["name_on_card"] = card_res["name_on_card"]
        order_status_data["card_reference"] = card_res["card_reference"]
        order_status_data["expiry_year"] = card_res["expiry_year"]
        order_status_data["expiry_month"] = card_res["expiry_month"]
        order_status_data["last_four_digits"] = card_res["last_four_digits"]
        order_status_data["saved_to_locker"] = card_res["saved_to_locker"]
        order_status_data["using_saved_card"] = card_res["using_saved_card"]
        order_status_data["card_issuer"] = card_res["card_issuer"]
        order_status_data["card_brand"] = card_res["card_brand"]
        order_status_data["card_type"] = card_res["card_type"]
        order_status_data["card_isin"] = card_res["card_isin"]
        order_status_data["card_fingerprint"] = card_res["card_fingerprint"]

    if order_status_res.get("refunds"):
        order_status_data["refunds"] = []
        for refund in order_status_res.get("refunds"):
            order_status_data["refunds"].append(
                {
                    "id": refund["id"],
                    "amount": refund["amount"],
                    "unique_request_id": refund["unique_request_id"],
                    "ref": refund["ref"],
                    "refund_time": utils.parse_utc_datetime(refund["created"]),
                    "status": refund["status"],
                    "error_message": refund["error_message"],
                    "sent_to_gateway": refund["sent_to_gateway"],
                    "initiated_by": refund["initiated_by"],
                    "refund_source": refund["refund_source"],
                    "refund_type": refund["refund_type"],
                    "error_code": refund["error_code"],
                    "metadata": refund["metadata"],
                }
            )

    # Cleanoff None values
    order_status_data = {k: v for k, v in order_status_data.items() if v is not None}

    return order_status_data, user_defined_values
