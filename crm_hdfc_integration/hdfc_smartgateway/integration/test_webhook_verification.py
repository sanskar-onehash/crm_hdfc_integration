"""Verify callback trust through the real status API/client with fake HTTP and DB."""

from contextlib import ExitStack
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from requests.exceptions import HTTPError, Timeout

from crm_hdfc_integration import utils as general_utils
from crm_hdfc_integration.hdfc_smartgateway.integration import client, service, webhook


class TestWebhookVerification(TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.order = Mock()
        self.order.name = "test-order"
        self.order.owner = "payer@example.invalid"
        self.order.customer = "Original Customer"
        self.order.hdfc_customer_id = "Cstored-gateway-id"
        self.order.currency = "INR"
        self.order.amount = 100
        self.order.hdfc_status = "NEW"
        self.order.order_status = "New"
        self.order.docstatus = 0
        self.order.get.side_effect = lambda key: getattr(self.order, key, None)

        def update(values):
            for key, value in values.items():
                setattr(self.order, key, value)

        self.order.update.side_effect = update
        self.order.save.return_value = self.order
        self.log = Mock()

        def get_doc(*args, **kwargs):
            return self.log if isinstance(args[0], dict) else self.order

        def throw(message):
            raise ValueError(message)

        self.form = frappe._dict(content={"order": {"order_id": "test-order"}})
        self.stack.enter_context(patch.object(frappe, "form_dict", self.form, create=True))
        self.stack.enter_context(patch.object(frappe, "throw", side_effect=throw))
        self.get_doc = self.stack.enter_context(patch.object(frappe, "get_doc", side_effect=get_doc))
        self.set_user = self.stack.enter_context(patch.object(frappe, "set_user"))
        self.publish = self.stack.enter_context(patch.object(frappe, "publish_realtime"))
        self.stack.enter_context(patch.object(general_utils, "parse_utc_datetime", return_value=None))
        self.stack.enter_context(patch.object(client.auth, "get_auth_details", return_value={"merchant_id": "test", "api_key": "test"}))
        self.stack.enter_context(patch.object(client.auth, "get_base_uri", return_value="https://example.invalid"))
        self.response = Mock()
        self.response.json.return_value = self.gateway_payload()
        self.http_get = self.stack.enter_context(patch.object(client.requests, "get", return_value=self.response))

    def gateway_payload(self, status="NEW", status_id=10):
        return {
            "order_id": "test-order", "status": status, "status_id": status_id,
            "amount": "100.00", "currency": "INR",
            **{f"udf{i}": "" for i in range(1, 11)},
        }

    def run_webhook(self):
        webhook.handle_order.__wrapped__()

    def assert_no_payment_changes(self):
        self.order.update.assert_not_called()
        self.order.save.assert_not_called()
        self.set_user.assert_not_called()
        self.publish.assert_not_called()

    def test_forged_success_uses_hdfc_new_status_without_posting(self):
        self.form.content["order"].update(status="CHARGED", status_id=21, amount=1, currency="USD")
        self.run_webhook()
        self.order.update.assert_not_called()
        self.order.save.assert_not_called()
        self.set_user.assert_not_called()
        self.assertEqual(self.order.docstatus, 0)
        sent = self.http_get.call_args
        self.assertEqual(sent.args[0], "https://example.invalid/orders/test-order")
        self.assertEqual(sent.kwargs["headers"]["x-customerid"], self.order.hdfc_customer_id)
        self.assertEqual(sent.kwargs["timeout"], (5, 20))
        logged = self.get_doc.call_args.args[0]["response"]
        self.assertEqual(logged["status"], "NEW")

    def test_verified_success_reaches_existing_submission(self):
        self.response.json.return_value = self.gateway_payload("CHARGED", 21)
        self.run_webhook()
        self.assertEqual(self.order.order_status, "Success")
        self.assertEqual(self.order.docstatus, 1)
        self.assertEqual(self.order.save.call_count, 2)
        self.set_user.assert_called_once_with("Administrator")
        self.publish.assert_called_once()

    def test_repeated_verified_success_does_not_submit_again(self):
        self.response.json.return_value = self.gateway_payload("CHARGED", 21)
        self.run_webhook()
        self.run_webhook()
        self.assertEqual(self.http_get.call_count, 2)
        self.assertEqual(self.order.save.call_count, 2)
        self.set_user.assert_called_once()

    def test_gateway_failure_wins_over_callback_claim(self):
        self.form.content["order"].update(status="CHARGED", status_id=21)
        self.response.json.return_value = self.gateway_payload("AUTHORIZATION_FAILED", 27)
        self.run_webhook()
        self.assertEqual(self.order.order_status, "Failed")
        self.assertEqual(self.order.docstatus, 0)
        self.set_user.assert_not_called()

    def test_mismatched_or_invalid_gateway_fields_do_not_change_order(self):
        for fields in (
            {"order_id": "different-order"}, {"amount": "99.99"},
            {"amount": "NaN"}, {"amount": None}, {"amount": "invalid"},
            {"currency": "USD"}, {"currency": "INR", "txn_detail": {"currency": "USD"}},
            {"currency": None}, {"status_id": 10}, {"status": "NEW"},
        ):
            with self.subTest(fields=fields):
                payload = self.gateway_payload("CHARGED", 21)
                payload.update(fields)
                self.response.json.return_value = payload
                with self.assertRaises(ValueError):
                    self.run_webhook()
                self.assert_no_payment_changes()
                self.log.save.assert_not_called()

    def test_success_accepts_transaction_currency_when_top_level_is_absent(self):
        payload = self.gateway_payload("CHARGED", 21)
        payload.pop("currency")
        payload["txn_detail"] = {"currency": "INR"}
        self.response.json.return_value = payload
        self.run_webhook()
        self.assertEqual(self.order.docstatus, 1)

    def test_pending_response_may_omit_currency_without_posting(self):
        self.response.json.return_value.pop("currency")
        self.run_webhook()
        self.order.save.assert_not_called()
        self.set_user.assert_not_called()

    def test_gateway_timeout_http_error_or_invalid_json_propagates_for_retry(self):
        for error in (Timeout("test"), HTTPError("test"), ValueError("invalid JSON")):
            with self.subTest(error=type(error).__name__):
                self.http_get.side_effect = error
                with self.assertRaises(type(error)):
                    self.run_webhook()
                self.assert_no_payment_changes()

    def test_non_success_http_response_cannot_post_its_body(self):
        self.response.json.return_value = self.gateway_payload("CHARGED", 21)
        self.response.raise_for_status.side_effect = HTTPError("test rejection")
        with self.assertRaises(HTTPError):
            self.run_webhook()
        self.response.json.assert_not_called()
        self.assert_no_payment_changes()

    def test_malformed_verified_response_does_not_post(self):
        for payload in (None, [], {**self.gateway_payload("CHARGED", 21), "txn_detail": "invalid"}):
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                with self.assertRaises(ValueError):
                    self.run_webhook()
                self.assert_no_payment_changes()

    def test_explicit_order_id_with_empty_internal_payload_still_fetches(self):
        service._sync_order_status(order_id="test-order", status_res={})
        self.http_get.assert_called_once()
        self.order.save.assert_not_called()

    def test_unknown_order_does_not_call_gateway_or_publish_success(self):
        self.get_doc.side_effect = LookupError("unknown order")
        with self.assertRaises(LookupError):
            self.run_webhook()
        self.http_get.assert_not_called()
        self.assert_no_payment_changes()

    def test_legacy_customer_id_is_preserved_for_status_lookup(self):
        self.order.hdfc_customer_id = None
        self.run_webhook()
        self.assertEqual(self.http_get.call_args.kwargs["headers"]["x-customerid"], self.order.customer)

    def test_internal_status_res_argument_cannot_bypass_gateway_verification(self):
        service._sync_order_status(status_res=self.gateway_payload("CHARGED", 21))
        self.http_get.assert_called_once()
        self.order.save.assert_not_called()

    def test_malformed_notifications_do_not_trigger_payment_changes(self):
        for content in (["invalid"], {"order": "invalid"}, {"order": {"status": "CHARGED"}}):
            with self.subTest(content=content):
                self.form.content = deepcopy(content)
                with self.assertRaises(ValueError):
                    self.run_webhook()
                self.assert_no_payment_changes()
        self.http_get.assert_not_called()

    def test_conflicting_internal_order_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            service._sync_order_status(order_id="test-order", status_res={"order_id": "other-order"})
        self.http_get.assert_not_called()
        self.assert_no_payment_changes()
