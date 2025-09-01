from crm_hdfc_integration.hdfc_smartgateway.integration import client

CHECKOUT_INTERFACE_ACTION = "paymentPage"


def create_order_session(
    order_id,
    amount,
    customer_details,
    return_url,
    page_client_id,
    currency=None,
    description=None,
    user_defined_parameters=None,
):
    action = CHECKOUT_INTERFACE_ACTION
    customer_id = customer_details.get("customer_id") or ""
    user_defined_parameters = user_defined_parameters or {}

    json_data = {
        **customer_details,
        **user_defined_parameters,
        "order_id": order_id,
        "amount": amount,
        "customer_id": customer_id,
        "action": action,
        "return_url": return_url,
        "payment_page_client_id": page_client_id,
        "currency": currency,
        "description": description,
    }

    # Remove None values
    json_data = {k: v for k, v in json_data.items() if v is not None}

    return client.make_post_request("/session", customer_id=customer_id, json=json_data)


def get_order_status(order_id, customer_id):
    return client.make_get_request(f"/orders/{order_id}", customer_id=customer_id)
