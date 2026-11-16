"""Invoice-charge regressions without a database or live gateway."""

import json
from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from crm_hdfc_integration.hdfc_smartgateway.doctype.hdfc_order import hdfc_order


class TestChargeCalculation(TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.invoice = frappe._dict(
            docstatus=1, status="Partly Paid", customer="Test Customer",
            currency="INR", company="Test Company", grand_total=10000,
            outstanding_amount=4000, party_account_currency="INR",
        )
        self.references = [{"invoice_type": "Sales Invoice", "invoice_id": "test-invoice"}]
        self.order = Mock()
        self.database = Mock()

        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                self.created_order = doctype
                return self.order
            return self.invoice

        def throw(message):
            raise ValueError(message)

        self.get_doc = self.stack.enter_context(patch.object(frappe, "get_doc", side_effect=get_doc))
        self.stack.enter_context(patch.object(frappe, "throw", side_effect=throw))
        self.stack.enter_context(patch.object(frappe, "db", self.database, create=True))
        self.stack.enter_context(patch.object(hdfc_order, "get_default_company", return_value="Test Company"))
        self.generate = self.stack.enter_context(patch.object(hdfc_order.service, "generate_order_id", return_value="test-order"))
        self.gateway = self.stack.enter_context(patch.object(hdfc_order.service, "create_order_session", return_value={
            "order_id": "test-order", "order_status": "New", "payment_link": "https://example.invalid/pay",
        }))

    def create(self, amount=0, **kwargs):
        arguments = dict(
            order_amount=amount, invoices=self.references,
            customer_details={"customer_id": "Test Customer"},
        )
        arguments.update(kwargs)
        return hdfc_order.create_order.__wrapped__(**arguments)

    def assert_no_gateway_or_insert(self):
        self.gateway.assert_not_called()
        self.order.insert.assert_not_called()
        self.database.commit.assert_not_called()

    def test_auto_charge_uses_remaining_balance(self):
        for amount in (0, "0", "", None):
            with self.subTest(amount=amount):
                self.create(amount)
                self.assertEqual(self.gateway.call_args.kwargs["amount"], 4000)
                self.assertEqual(self.created_order["amount"], 4000)

    def test_unpaid_invoice_keeps_full_balance_charge(self):
        self.invoice.update(status="Unpaid", outstanding_amount=10000)
        self.create()
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 10000)

    def test_partial_and_exact_balance_payments_are_preserved(self):
        for amount in (1000, "3999.99", 4000):
            with self.subTest(amount=amount):
                self.create(amount)
                self.assertEqual(self.gateway.call_args.kwargs["amount"], float(amount))

    def test_amount_above_balance_is_rejected_before_gateway(self):
        for amount in (4000.01, 10000):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(ValueError, "exceeds the outstanding balance"):
                    self.create(amount)
                self.assert_no_gateway_or_insert()

    def test_duplicate_invoice_is_rejected_before_gateway(self):
        with self.assertRaisesRegex(ValueError, "Duplicate invoice"):
            self.create(invoices=self.references * 2)
        self.assert_no_gateway_or_insert()

    def test_multiple_invoices_sum_outstanding_not_original_totals(self):
        self.create(invoices=self.references + [{"invoice_type": "Sales Invoice", "invoice_id": "second-invoice"}])
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 8000)
        self.assertEqual(len(self.created_order["reference_invoices"]), 2)

    def test_decimal_balances_do_not_accumulate_float_comparison_errors(self):
        first = frappe._dict(self.invoice, outstanding_amount=0.1)
        second = frappe._dict(self.invoice, outstanding_amount=0.2)

        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                self.created_order = doctype
                return self.order
            return first if name == "test-invoice" else second

        self.get_doc.side_effect = get_doc
        references = self.references + [{"invoice_type": "Sales Invoice", "invoice_id": "second-invoice"}]
        self.create("0.30", invoices=references)
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 0.3)
        self.create(0.1 + 0.2, invoices=references)
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 0.3)
        self.create(0, invoices=references)
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 0.3)

    def test_zero_negative_missing_or_invalid_balance_is_rejected(self):
        for balance in (0, -1, None, "invalid", "NaN", "Infinity"):
            with self.subTest(balance=balance):
                self.invoice.outstanding_amount = balance
                with self.assertRaises(ValueError):
                    self.create()
                self.assert_no_gateway_or_insert()

    def test_sub_paise_explicit_payment_cannot_become_full_balance(self):
        for amount in ("0.001", "-0.001"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    self.create(amount)
                self.assert_no_gateway_or_insert()

    def test_float_noise_is_rounded_but_a_real_paise_overpayment_is_rejected(self):
        self.create(4000.000000000001)
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 4000)
        self.gateway.reset_mock()
        self.order.insert.reset_mock()
        self.database.commit.reset_mock()
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.create("4000.01")
        self.assert_no_gateway_or_insert()

    def test_invalid_amount_does_not_default_to_full_balance(self):
        for amount in (-1, "invalid", "NaN", "Infinity", "-Infinity", "1e9999"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    self.create(amount)
                self.assert_no_gateway_or_insert()

    def test_paid_or_unsubmitted_invoice_remains_rejected(self):
        for status, docstatus in (("Paid", 1), ("Unpaid", 0), ("Cancelled", 2)):
            with self.subTest(status=status, docstatus=docstatus):
                self.invoice.update(status=status, docstatus=docstatus)
                with self.assertRaises(ValueError):
                    self.create()
                self.assert_no_gateway_or_insert()

    def test_customer_currency_and_company_mismatches_remain_rejected(self):
        for overrides in ({"customer": "Different Customer"}, {"currency": "USD"}):
            with self.subTest(overrides=overrides):
                with patch.dict(self.invoice, overrides):
                    with self.assertRaises(ValueError):
                        self.create()
                self.assert_no_gateway_or_insert()
        second = frappe._dict(self.invoice, company="Different Company")
        self.get_doc.side_effect = [self.invoice, second]
        with self.assertRaises(ValueError):
            self.create(invoices=self.references + [{"invoice_type": "Sales Invoice", "invoice_id": "second-invoice"}])
        self.assert_no_gateway_or_insert()

    def test_customer_inferred_from_invoice_reaches_order_and_gateway(self):
        self.create(customer_details={"customer_name": "Test Customer"})
        self.assertEqual(self.created_order["customer"], "Test Customer")
        self.assertEqual(self.gateway.call_args.kwargs["customer_details"]["customer_id"], "Test Customer")

    def test_json_portal_inputs_remain_supported(self):
        self.create("2000", invoices=json.dumps(self.references), customer_details=json.dumps({"customer_id": "Test Customer"}))
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 2000)

    def test_outstanding_in_different_account_currency_is_not_mischarged(self):
        self.invoice.party_account_currency = "USD"
        with self.assertRaisesRegex(ValueError, "account currencies must match"):
            self.create()
        self.assert_no_gateway_or_insert()

    def test_positive_order_without_invoices_is_preserved(self):
        self.create("123.45", invoices=[])
        self.assertEqual(self.gateway.call_args.kwargs["amount"], 123.45)

    def test_zero_order_without_invoices_remains_rejected(self):
        with self.assertRaises(ValueError):
            self.create(0, invoices=[])
        self.assert_no_gateway_or_insert()
