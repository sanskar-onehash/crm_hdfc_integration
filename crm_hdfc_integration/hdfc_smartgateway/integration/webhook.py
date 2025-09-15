import frappe
from crm_hdfc_integration.hdfc_smartgateway.integration import service, utils


@frappe.whitelist(allow_guest=True)
def handle_order():
    content = frappe.form_dict.get("content") or {}

    if content.get("order"):
        order_doc = service._sync_order_status(status_res=content.get("order"))

        frappe.publish_realtime(
            utils.HDFC_WH_ORDER_UDPATED,
            {"order_id": order_doc.name},
            user=order_doc.owner,
            after_commit=True,
        )
