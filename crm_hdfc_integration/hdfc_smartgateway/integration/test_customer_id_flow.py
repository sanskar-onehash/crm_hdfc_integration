"""Payment-boundary regressions; run without a site or real gateway requests."""

import unittest
from unittest.mock import Mock, patch

import frappe

from crm_hdfc_integration.hdfc_smartgateway.doctype.hdfc_order import hdfc_order
from crm_hdfc_integration.hdfc_smartgateway.integration import api, client, service, utils


class TestCustomerIDFlow(unittest.TestCase):
    def test_create_order_reaches_http_client_and_stores_matching_gateway_id(self):
        for customer_id in ("Existing Customer", "Parent \u00e9", "A" * 33):
            with self.subTest(customer_id=customer_id):
                customer_details = {
                    "customer_id": customer_id,
                    "customer_name": customer_id,
                }
                expected_id = utils.get_hdfc_customer_id(customer_id)
                order = Mock()
                database = Mock()
                database.get_single_value.return_value = "test-client"
                response = Mock()
                response.json.return_value = {"status": "NEW"}
                session = {
                    "order_id": "test-order",
                    "order_status": "New",
                    "payment_link": "https://example.invalid/pay",
                    "sdk_payload": {},
                }

                with (
                    patch.object(frappe.local, "flags", frappe._dict(in_test=True), create=True),
                    patch.object(hdfc_order, "get_default_company", return_value="Test"),
                    patch.object(frappe, "get_doc", return_value=order) as get_doc,
                    patch.object(frappe, "db", database, create=True),
                    patch.object(service, "generate_order_id", return_value="test-order"),
                    patch.object(utils, "get_return_url", return_value="https://example.invalid/return"),
                    patch.object(service.transformers, "parse_session_res", return_value=session),
                    patch.object(client.auth, "get_base_uri", return_value="https://example.invalid"),
                    patch.object(client.auth, "get_auth_details", return_value={"merchant_id": "test", "api_key": "test"}),
                    patch.object(client.requests, "post", return_value=response) as post,
                ):
                    result = hdfc_order.create_order(
                        order_amount=100, customer_details=customer_details
                    )

                sent = post.call_args.kwargs
                self.assertEqual(sent["json"]["customer_id"], expected_id)
                self.assertEqual(sent["headers"]["x-customerid"], expected_id)
                self.assertEqual(sent["json"]["customer_name"], customer_id)
                self.assertEqual(get_doc.call_args.args[0]["customer"], customer_id)
                self.assertEqual(order.update.call_args.args[0]["hdfc_customer_id"], expected_id)
                self.assertEqual(customer_details["customer_id"], customer_id)
                self.assertEqual(result["payment_link"], session["payment_link"])
                order.insert.assert_called_once()
                database.commit.assert_called_once()

    def test_direct_session_call_imports_normalizer_and_preserves_input(self):
        details = {"customer_id": "Parent \u00e9"}
        with patch.object(client, "make_post_request") as post:
            api.create_order_session("test-order", 100, details, "return", "client")
        expected_id = utils.get_hdfc_customer_id(details["customer_id"])
        self.assertEqual(post.call_args.kwargs["customer_id"], expected_id)
        self.assertEqual(post.call_args.kwargs["json"]["customer_id"], expected_id)
        self.assertEqual(details, {"customer_id": "Parent \u00e9"})

    def test_status_uses_saved_gateway_id_and_legacy_fallback(self):
        for saved_id in ("C123", None):
            with self.subTest(saved_id=saved_id):
                order = frappe._dict(
                    customer="Legacy Customer", hdfc_customer_id=saved_id,
                    hdfc_status="NEW", name="test-order", amount=100, currency="INR",
                )
                log = Mock()
                with (
                    patch.object(frappe, "get_doc", side_effect=[order, log]),
                    patch.object(api, "get_order_status", return_value={"order_id": "test-order", "amount": 100, "status": "NEW"}) as status,
                    patch.object(service.transformers, "parse_order_status_res", return_value=({"hdfc_status": "NEW"}, None)),
                ):
                    service._sync_order_status("test-order")
                status.assert_called_once_with("test-order", saved_id or "Legacy Customer")


if __name__ == "__main__":
    unittest.main()
