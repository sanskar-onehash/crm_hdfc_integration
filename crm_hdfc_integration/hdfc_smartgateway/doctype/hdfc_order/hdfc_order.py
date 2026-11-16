# Copyright (c) 2025, OneHash and contributors
# For license information, please see license.txt

import frappe
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import isfinite
from frappe.model.document import Document
from crm_hdfc_integration import utils
from crm_hdfc_integration.hdfc_smartgateway.integration import service
from crm_hdfc_integration.hdfc_smartgateway.integration import utils as gateway_utils
from erpnext import get_default_company
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


class HDFCOrder(Document):

    def autoname(self):
        if not self.order_id:
            self.order_id = service.generate_order_id()
        self.name = self.order_id

    def before_save(self):
        if self.get("reference_fieldname") or self.get("reference_pe_fieldname"):
            if not (self.get("reference_type") or self.get("reference_doc")):
                frappe.throw("Reference Type and Doc are required.")

    def before_submit(self):
        if self.order_status != "Success":
            frappe.throw("Order status should be Success to submit the order.")

        pe = self.create_order_pe(ignore_permissions=True)
        pe.run_method("before_submit")
        pe = pe.save(ignore_permissions=True)

        self.set("payment_entry", pe.name)

        reference_pe_fieldname = self.get("reference_pe_fieldname")
        if reference_pe_fieldname:
            reference_doc = frappe.get_doc(
                self.get("reference_type"), self.get("reference_doc")
            )
            reference_doc.set(reference_pe_fieldname, pe.name)
            reference_doc.save(ignore_permissions=True)

    def before_insert(self):
        reference_fieldname = self.get("reference_fieldname")
        if reference_fieldname:
            reference_doc = frappe.get_doc(
                self.get("reference_type"), self.get("reference_doc")
            )
            reference_doc.set(reference_fieldname, self.name)
            reference_doc.save(ignore_permissions=True)

    def create_order_pe(self, ignore_permissions=False):
        pe = get_payment_entry(
            self.doctype,
            self.name,
            party_amount=self.amount,
            party_type="Customer",
            payment_type="Receive",
            reference_date=self.txn_date,
            ignore_permissions=ignore_permissions,
        )

        # get_payment_entry sets HDFC Order as reference
        pe.update(
            {
                "references": [],
                "docstatus": 1,
                "owner": self.owner,
                "reference_no": self.txn_id,
            }
        )

        total_amount = self.amount
        for invoice in self.get("reference_invoices") or []:
            invoice_type = invoice.get("invoice_type")
            invoice_name = invoice.get("invoice")
            invoice_amount = frappe.db.get_value(
                invoice_type, invoice_name, "outstanding_amount"
            )

            allocated_amount = (
                invoice_amount if invoice_amount <= total_amount else total_amount
            )
            total_amount -= allocated_amount

            pe.append(
                "references",
                {
                    "reference_doctype": invoice_type,
                    "reference_name": invoice_name,
                    "allocated_amount": allocated_amount,
                },
            )

        return pe


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
    reference_pe_fieldname=None,
    success_url=None,
    failed_url=None,
    user_defined_parameters=None,
):
    customer_details = utils.ensure_parsed(customer_details)
    invoices = utils.ensure_parsed(invoices)
    # Zero/omitted amounts still mean "pay all referenced outstanding balances".
    # Invalid input must not silently turn into zero and charge the full balance.
    order_amount = _parse_amount(
        0 if order_amount is None or order_amount == "" else order_amount,
        "Order amount",
    )
    if order_amount < 0:
        frappe.throw("Order amount must be greater than zero.")

    customer_id = customer_details.get("customer_id")
    invoices = invoices or []
    company = None

    if invoices:
        parsed = parse_reference_invoices(invoices, order_currency, customer_id)
        if not order_amount:
            order_amount = _parse_amount(parsed["amount"], "Outstanding amount")
        elif order_amount > _parse_amount(parsed["amount"], "Outstanding amount"):
            frappe.throw("Order amount exceeds the outstanding balance of the selected invoices.")
        order_currency = parsed["currency"]
        customer_id = parsed["customer"]
        customer_details = {**customer_details, "customer_id": customer_id}
        invoices = parsed["invoices"]
        company = parsed["company"]
    elif not order_amount:
        frappe.throw("Either invoices or order_amount must be provided.")

    order_amount = float(order_amount)

    if not company:
        company = get_default_company()

    order_id = service.generate_order_id()

    if success_url:
        separator = "&" if "?" in success_url else "?"
        success_url += f"{separator}order_id={order_id}"

    if failed_url:
        separator = "&" if "?" in failed_url else "?"
        failed_url += f"{separator}order_id={order_id}"

    order_doc = frappe.get_doc(
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
            "reference_pe_fieldname": reference_pe_fieldname,
            "user_defined_parameters": frappe.json.dumps(user_defined_parameters),
            "payment_description": description,
            "success_url": success_url,
            "failed_url": failed_url,
        }
    )

    if not order_doc.has_permission("create"):
        frappe.throw("User don't have permissions for HDFC Order.")

    hdfc_customer_id = gateway_utils.get_hdfc_customer_id(customer_id)
    hdfc_customer_details = {**customer_details, "customer_id": hdfc_customer_id}

    hdfc_order = service.create_order_session(
        amount=order_amount,
        customer_details=hdfc_customer_details,
        order_id=order_id,
        currency=order_currency,
        description=description,
        user_defined_parameters=user_defined_parameters,
    )

    order_doc.update(
        {
            "order_status": hdfc_order.get("order_status"),
            "payment_link": hdfc_order.get("payment_link"),
            "payment_link_expiry": hdfc_order.get("payment_link_expiry"),
            "sdk_payload": frappe.json.dumps(hdfc_order.get("sdk_payload")),
            "hdfc_customer_id": hdfc_customer_id,
        }
    )

    order_doc.insert()
    frappe.db.commit()

    if hdfc_order.get("order_status") == "New":
        return {
            "order_id": hdfc_order.get("order_id"),
            "payment_link": hdfc_order.get("payment_link"),
        }
    return {"order_id": hdfc_order.get("order_id")}


def parse_reference_invoices(
    reference_invoices: list[dict],
    currency: str,
    customer_id: str | None = None,
):
    amount = Decimal("0")
    company = None
    parsed_invoices = []
    seen_invoices = set()

    for invoice in reference_invoices:
        invoice_type = invoice.get("invoice_type", "")
        invoice_id = invoice.get("invoice_id", "")
        invoice_key = (invoice_type, invoice_id)
        if invoice_key in seen_invoices:
            frappe.throw("Duplicate invoice references are not allowed.")
        seen_invoices.add(invoice_key)
        invoice_doc = frappe.get_doc(invoice_type, invoice_id)
        if invoice_doc.docstatus != 1:
            frappe.throw(f"Invoice {invoice_type}:{invoice_id} is not submitted.")
        if invoice_doc.status == "Paid":
            frappe.throw("Invoice is already paid.")

        invoice_customer = utils.get_or_throw(invoice_doc, "customer")
        invoice_currency = utils.get_or_throw(invoice_doc, "currency")
        # Outstanding amounts are denominated in the receivable account's
        # currency. Do not charge those units as the invoice currency.
        account_currency = invoice_doc.get("party_account_currency")
        if account_currency and account_currency != invoice_currency:
            frappe.throw("Invoice and receivable account currencies must match for portal payment.")
        invoice_amount = _parse_amount(invoice_doc.get("outstanding_amount"), "Outstanding amount")
        if invoice_amount <= 0:
            frappe.throw("Selected invoice has no positive outstanding balance.")
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
        "amount": float(amount),
        "customer": customer_id,
        "invoices": parsed_invoices,
        "company": company,
    }


def _parse_amount(value, label):
    """Validate monetary input without silently substituting a full charge."""
    try:
        amount = Decimal(str(value))
        valid = amount.is_finite() and isfinite(float(amount))
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        valid = False
    if not valid:
        frappe.throw(f"{label} must be a valid finite number.")
    try:
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        frappe.throw(f"{label} is outside the supported payment range.")
    # Compare and send the same two-decimal amount supported by the gateway.
    # In particular, never turn a tiny explicit payment into the zero sentinel
    # that means "charge the entire outstanding balance".
    if amount != 0 and rounded == 0:
        frappe.throw(f"{label} must be at least 0.01.")
    return rounded
