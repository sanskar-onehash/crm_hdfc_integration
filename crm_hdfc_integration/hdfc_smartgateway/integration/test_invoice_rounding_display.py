"""Rounding is an invoice adjustment, not a payment."""

import ast
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from unittest import TestCase

from crm_hdfc_integration.deployment.portal_payment_flow import (
    NEW_INVOICE_AMOUNT, OLD_INVOICE_AMOUNT, patch_invoice_script,
)


class TestInvoiceRoundingDisplay(TestCase):
    def calculations(self, code, **overrides):
        values = dict(
            currency="INR", party_account_currency="INR", grand_total=16046.3,
            base_grand_total=16046.3, rounded_total=16046,
            base_rounded_total=16046, disable_rounded_total=0,
            payable_amount=16046,
        )
        values.update(overrides)
        utility = SimpleNamespace(flt=lambda amount, precision: round(float(amount), precision))
        scope = {"invoice": SimpleNamespace(**values), "frappe": SimpleNamespace(utils=utility), "frappe_utils": utility}
        exec(dedent(code), scope)
        return scope

    def test_rounding_only_does_not_show_a_payment(self):
        result = self.calculations(NEW_INVOICE_AMOUNT)
        self.assertEqual(result["amount_paid"], 0)
        self.assertEqual(result["rounding_adjustment"], -0.30)
        self.assertEqual(result["effective_total"], 16046)

    def test_real_partial_payment_excludes_rounding(self):
        result = self.calculations(NEW_INVOICE_AMOUNT, payable_amount=12046)
        self.assertEqual(result["amount_paid"], 4000)
        self.assertEqual(result["rounding_adjustment"], -0.30)

    def test_rounding_up_and_disabled_rounding(self):
        result = self.calculations(NEW_INVOICE_AMOUNT, grand_total=16046.7, rounded_total=16047, payable_amount=16047)
        self.assertEqual(result["amount_paid"], 0)
        self.assertEqual(result["rounding_adjustment"], 0.30)
        result = self.calculations(NEW_INVOICE_AMOUNT, disable_rounded_total=1, payable_amount=16046.3)
        self.assertEqual(result["amount_paid"], 0)
        self.assertEqual(result["rounding_adjustment"], 0)

    def test_totals_use_the_same_currency_as_the_outstanding_balance(self):
        result = self.calculations(NEW_INVOICE_AMOUNT, currency="USD", party_account_currency="USD", grand_total=100, rounded_total=100, base_grand_total=8300, base_rounded_total=8300, payable_amount=40)
        self.assertEqual(result["amount_paid"], 60)
        result = self.calculations(NEW_INVOICE_AMOUNT, currency="USD", party_account_currency="INR", grand_total=100, rounded_total=100, base_grand_total=8300, base_rounded_total=8300, payable_amount=8300)
        self.assertEqual(result["amount_paid"], 0)
        self.assertEqual(result["invoice_total"], 8300)

    def test_local_invoice_api_matches_the_native_override_calculation(self):
        root = Path(__file__).resolve().parents[4]
        source = (root / "onehash_education/onehash_education/api.py").read_text()
        function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "get_invoices_to_pay")
        fields = {"same_currency", "invoice_total", "rounded_total", "effective_total", "amount_paid", "rounding_adjustment"}
        statements = [node for node in ast.walk(function) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in fields for target in node.targets)]
        code = "\n".join(ast.get_source_segment(source, node) for node in sorted(statements, key=lambda node: node.lineno))
        result = self.calculations(code)
        self.assertEqual(result["amount_paid"], 0)
        self.assertEqual(result["rounding_adjustment"], -0.30)

    def test_unexpected_native_override_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            patch_invoice_script(OLD_INVOICE_AMOUNT)
