import frappe
from frappe.auth import LoginManager
from crm_hdfc_integration.hdfc_smartgateway.integration import utils, api, transformers


def generate_order_id():
    return utils.generate_order_id()


def create_order_session(
    amount,
    customer_details,
    order_id=None,
    currency=None,
    description=None,
    user_defined_parameters=None,
):
    page_client_id = frappe.db.get_single_value(
        "HDFC SmartGateway Settings", "api_base_uri"
    )

    if not order_id:
        order_id = generate_order_id()

    session_res = api.create_order_session(
        order_id,
        amount,
        customer_details,
        utils.get_return_url(),
        page_client_id,
        currency=currency,
        description=description,
        user_defined_parameters=user_defined_parameters,
    )
    session_data = transformers.parse_session_res(session_res)

    return session_data


def get_order_status(order_id, customer_id):
    status_res = api.get_order_status(order_id, customer_id)
    order_status_data = transformers.parse_order_status_res(status_res)

    return order_status_data


@frappe.whitelist(allow_guest=True)
def verify_order():
    frappe.form_dict.pop("cmd")
    signature_algorithm = frappe.form_dict.pop("signature_algorithm")
    signature = frappe.form_dict.pop("signature")
    order_id = frappe.form_dict.get("order_id")

    if not signature_algorithm:
        frappe.throw("Signature algorithm is required")
    if not signature:
        frappe.throw("Signature is required.")
    if not order_id:
        frappe.throw("Order Id is required.")
    if signature_algorithm != "HMAC-SHA256":
        frappe.log_error(
            "HDFC Order verification invalid algorithm",
            f"algorithm: {signature_algorithm} is not currently supported",
        )
        frappe.throw(f"algorithm: {signature_algorithm} is not currently supported")

    gateway_settings = utils.get_smartgateway_settings()

    is_valid_payload = utils.verify_hmac_signature(
        signature, frappe.form_dict, gateway_settings.response_key
    )
    if not is_valid_payload:
        frappe.throw("Unathorized, Signature verification failed.")

    order_doc = frappe.get_doc("HDFC Order", order_id)

    new_status = transformers.get_system_status_for_id(
        frappe.form_dict.get("status_id")
    )

    if new_status and order_doc.order_status != new_status:
        _sync_order_status(order_id, True)

    # FIXME: Assuming owner of hdfc order will be the payer
    # The following workaround is done as user session is lost
    # in hdfc return url, which is handled in this function
    user_session_id = utils.get_user_active_sid(order_doc.owner)
    redirect_url = order_doc.success_url or frappe.utils.get_url()

    frappe.local.form_dict.sid = user_session_id
    frappe.local.login_manager = LoginManager()

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = redirect_url


@frappe.whitelist()
def sync_order_status(order_id):
    _sync_order_status(order_id)


def _sync_order_status(order_id, ignore_permissions=False):
    order_doc = frappe.get_doc("HDFC Order", order_id)

    status_res = api.get_order_status(order_id, order_doc.customer)
    status_data, _ = transformers.parse_order_status_res(status_res)

    if not status_data.get("status"):
        return

    if order_doc.order_status != status_data["status"]:
        order_doc.update(status_data)
        order_doc.save(ignore_permissions=ignore_permissions)

        if status_data["status"] == "Success":
            frappe.set_user("Administrator")
            order_doc.docstatus = 1
            order_doc._action = "submit"
            order_doc.save(ignore_permissions=ignore_permissions)
