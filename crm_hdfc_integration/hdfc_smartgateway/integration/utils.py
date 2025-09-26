import frappe
from base64 import b64encode
from hmac import new as hmac
from hashlib import sha256
from urllib.parse import quote_plus
from frappe.query_builder import Order

ORDER_ID_LENGTH = 15  # 20; -5 for order
HDFC_WH_ORDER_UPDATED = "HDFC_ORDER_UPDATED_WH"


def generate_order_id():
    return "order" + frappe.generate_hash(length=ORDER_ID_LENGTH)


def get_smartgateway_settings():
    smartgateway_settings = frappe.get_single("HDFC SmartGateway Settings")
    if not smartgateway_settings.enabled:
        frappe.throw("HDFC SmartGateway is not enabled")

    return smartgateway_settings


def verify_hmac_signature(signature, params, key):
    if isinstance(key, str):
        key = key.encode("utf-8")
    encoded_sorted = []
    for i in sorted(params.keys()):
        encoded_sorted.append(quote_plus(i) + "=" + quote_plus(params.get(i)))

    encoded_string = quote_plus("&".join(encoded_sorted))
    dig = hmac(key, msg=encoded_string.encode("utf-8"), digestmod=sha256).digest()

    return b64encode(dig).decode() == signature


def get_return_url():
    return f"{frappe.utils.get_url()}/api/method/crm_hdfc_integration.hdfc_smartgateway.integration.service.verify_order"


def get_user_active_sid(user):
    session = frappe.qb.DocType("Sessions")
    session_ids = (
        frappe.qb.from_(session)
        .where((session.user == user) & (session.status == "Active"))
        .select(session.sid)
        .limit(1)
        .orderby(session.lastupdate, order=Order.desc)
    ).run(as_dict=True)

    if len(session_ids):
        return session_ids[0]["sid"]
    return None
