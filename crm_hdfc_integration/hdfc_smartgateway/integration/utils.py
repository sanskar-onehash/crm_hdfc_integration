import frappe

ORDER_ID_LENGTH = 15  # 20; -5 for order


def generate_order_id():
    return "order" + frappe.generate_hash(length=ORDER_ID_LENGTH)


def get_smartgateway_settings():
    smartgateway_settings = frappe.get_single("HDFC SmartGateway Settings")
    if not smartgateway_settings.enabled:
        frappe.throw("HDFC SmartGateway is not enabled")

    return smartgateway_settings
