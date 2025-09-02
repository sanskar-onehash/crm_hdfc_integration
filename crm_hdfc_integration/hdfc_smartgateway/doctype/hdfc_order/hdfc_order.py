# Copyright (c) 2025, OneHash and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from crm_hdfc_integration import utils
from crm_hdfc_integration.hdfc_smartgateway.integration import service
from erpnext import get_default_company


class HDFCOrder(Document):

    def autoname(self):
        if not self.order_id:
            self.order_id = service.generate_order_id()
        self.name = self.order_id

    def before_submit(self):
        if not self.get("payment_entry"):
            frappe.throw("Payment Entry is required to submit CF Order")


@frappe.whitelist()
def create_order(
    order_currency="INR",
    order_amount=0,
    customer_details={},
    invoices=None,
    description=None,
    reference_doctype=None,
    reference_name=None,
    reference_fieldname=None,
    return_url=None,
    user_defined_parameters=None,
):
    if not return_url:
        frappe.throw("return_url is mandatory.")

    customer_details = utils.ensure_parsed(customer_details)
    invoices = utils.ensure_parsed(invoices)

    customer_id = customer_details.get("customer_id")
    invoices = invoices or []
    company = None

    if invoices:
        parsed = parse_reference_invoices(invoices, order_currency, customer_id)
        order_amount = parsed["amount"]
        order_currency = parsed["currency"]
        invoices = parsed["invoices"]
        company = parsed["company"]
    elif not order_amount:
        frappe.throw("Either invoices or order_amount must be provided.")

    if not company:
        company = get_default_company()

    order_id = service.generate_order_id()

    hdfc_order = service.create_order_session(
        amount=order_amount,
        customer_details=customer_details,
        return_url=return_url,
        order_id=order_id,
        currency=order_currency,
        description=description,
        user_defined_parameters=user_defined_parameters,
    )

    frappe.get_doc(
        {
            "doctype": "HDFC Order",
            "order_id": order_id,
            "currency": order_currency,
            "amount": order_amount,
            "customer": customer_id,
            "reference_invoices": invoices,
            "company": company,
            "reference_type": reference_doctype,
            "reference_doc": reference_name,
            "reference_fieldname": reference_fieldname,
            "user_defined_parameters": frappe.json.dumps(user_defined_parameters),
            "payment_description": description,
            "order_status": hdfc_order.get("order_status"),
            "payment_link": hdfc_order.get("payment_link"),
            "payment_link_expiry": hdfc_order.get("payment_link_expiry"),
            "sdk_payload": frappe.json.dumps(hdfc_order.get("sdk_payload")),
        }
    ).insert()
    frappe.db.commit()

    if hdfc_order.get("order_status") == "New":
        return hdfc_order.get("payment_link")
    return None


def parse_reference_invoices(
    reference_invoices: list[dict],
    currency: str,
    customer_id: str | None = None,
):
    amount = 0
    company = None
    parsed_invoices = []

    for invoice in reference_invoices:
        invoice_type = invoice.get("invoice_type", "")
        invoice_id = invoice.get("invoice_id", "")
        invoice_doc = frappe.get_doc(invoice_type, invoice_id)
        if invoice_doc.docstatus != 1:
            frappe.throw(f"Invoice {invoice_type}:{invoice_id} is not submitted.")

        invoice_customer = utils.get_or_throw(invoice_doc, "customer")
        invoice_currency = utils.get_or_throw(invoice_doc, "currency")
        invoice_amount = utils.get_or_throw(invoice_doc, "grand_total")
        invoice_company = utils.get_or_throw(invoice_doc, "company")

        amount += invoice_amount
        if not customer_id:
            customer_id = invoice_customer
        if not currency:
            currency = invoice_currency
        if not company:
            company = invoice_company

        if customer_id != invoice_customer:
            frappe.throw("Customer doesn't matches across invoices.")
        if currency != invoice_currency:
            frappe.throw("Currency doesn't matches across invoices.")
        if company != invoice_company:
            frappe.throw("Company doesn't matches across invoices.")

        parsed_invoices.append({"invoice_type": invoice_type, "invoice": invoice_id})

    return {
        "currency": currency,
        "amount": amount,
        "customer": customer_id,
        "invoices": parsed_invoices,
        "company": company,
    }
