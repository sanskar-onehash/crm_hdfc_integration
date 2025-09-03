import frappe
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


def verify_order():
    pass


def sync_order_status(order_id):
    pass
