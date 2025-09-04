import frappe

from crm_hdfc_integration.config import config


def after_install():
    add_hdfc_mops()

    frappe.db.commit()


def add_hdfc_mops():
    for mode in config.HDFC_MODE_OF_PAYMENTS:
        if not frappe.db.exists("Mode of Payment", mode.get("mode_of_payment")):
            frappe.get_doc({"doctype": "Mode of Payment", **mode}).insert()
