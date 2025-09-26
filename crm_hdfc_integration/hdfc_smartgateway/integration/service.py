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
        _sync_order_status(order_id)

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
def sync_order_status(order_id, status=None):
    order_doc = _sync_order_status(order_id)

    if status is None or order_doc.order_status != status:
        return order_doc.as_dict(convert_dates_to_str=True)

    return None


def _sync_order_status(order_id=None, status_res=None):
    order_doc = None
    if not status_res:
        if not order_id:
            frappe.throw("Order id is required.")

        order_doc = frappe.get_doc("HDFC Order", order_id)

        status_res = api.get_order_status(order_id, order_doc.customer)

        # Maintain Order Status Response log
        frappe.get_doc(
            {
                "doctype": "HDFC Order Status Logs",
                "order": order_id,
                "response": status_res,
            }
        ).save(ignore_permissions=True)
    else:
        order_doc = frappe.get_doc("HDFC Order", status_res.get("order_id"))

    if not order_doc:
        frappe.throw("No Order Found.")

    status_data, _ = transformers.parse_order_status_res(status_res)

    if (
        status_data.get("hdfc_status")
        and order_doc.hdfc_status != status_data["hdfc_status"]
    ):
        order_doc.update(status_data)
        order_doc = order_doc.save(ignore_permissions=True)

        if status_data["order_status"] == "Success":
            frappe.set_user("Administrator")
            order_doc.docstatus = 1
            order_doc._action = "submit"
            order_doc = order_doc.save(ignore_permissions=True)

    return order_doc
