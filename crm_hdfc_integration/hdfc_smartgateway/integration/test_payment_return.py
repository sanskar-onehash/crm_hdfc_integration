"""Return-flow regressions without a site, gateway request, or accounting writes."""

from base64 import b64encode
from contextlib import ExitStack
from hashlib import sha256
from hmac import new as hmac
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, quote_plus, urlparse

import frappe
from frappe.auth import CookieManager
from werkzeug.wrappers import Response

from crm_hdfc_integration.hdfc_smartgateway.integration import service


class TestPaymentReturn(TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.form = frappe._dict(order_id="test-order", status_id="31")
        self.session = frappe._dict(user="Guest", sid="Guest")
        self.request = SimpleNamespace(cookies={}, scheme="https", method="POST")
        self.cookie_manager = CookieManager()
        self.local = SimpleNamespace(
            form_dict=self.form, response={}, cookie_manager=self.cookie_manager
        )
        self.order = frappe._dict(
            owner="payer@example.invalid", order_status="New",
            success_url="https://example.invalid/success",
            failed_url="https://example.invalid/retry?order_id=test-order",
        )
        for name, value in (
            ("local", self.local), ("form_dict", self.form),
            ("session", self.session), ("request", self.request),
        ):
            self.stack.enter_context(patch.object(frappe, name, value, create=True))
        self.get_doc = self.stack.enter_context(
            patch.object(frappe, "get_doc", return_value=self.order)
        )
        self.stack.enter_context(patch.object(frappe.utils, "get_url", return_value="https://example.invalid"))
        def throw(message):
            raise ValueError(message)

        self.stack.enter_context(patch.object(frappe, "throw", side_effect=throw))
        self.settings = self.stack.enter_context(
            patch.object(service.utils, "get_smartgateway_settings", return_value=frappe._dict(response_key="test-key"))
        )
        self.sync = self.stack.enter_context(patch.object(service, "_sync_order_status", return_value=self.order))
        self.lookup_sid = self.stack.enter_context(patch.object(service.utils, "get_user_active_sid", return_value="test-owner-sid"))
        self.login = self.stack.enter_context(patch.object(service, "LoginManager"))

    def run_return(self):
        # Exercise the actual handler; only the request decorator is bypassed.
        service.verify_order.__wrapped__()

    def assert_no_unsigned_payment_or_login(self):
        self.sync.assert_not_called()
        self.lookup_sid.assert_not_called()
        self.login.assert_not_called()
        self.settings.assert_not_called()
        self.assertNotIn("sid", self.form)

    def sign_return(self, status_id="21"):
        self.form.status_id = status_id
        encoded = "&".join(
            quote_plus(key) + "=" + quote_plus(value)
            for key, value in sorted(self.form.items())
        )
        digest = hmac(b"test-key", quote_plus(encoded).encode(), sha256).digest()
        self.form.signature_algorithm = "HMAC-SHA256"
        self.form.signature = b64encode(digest).decode()

    def test_active_session_returns_directly_to_retry(self):
        self.session.update(user=self.order.owner, sid="current-browser-sid")
        self.run_return()
        self.assertEqual(self.local.response["location"], self.order.failed_url)
        self.assertEqual(self.session.sid, "current-browser-sid")
        self.assert_no_unsigned_payment_or_login()

    def test_cross_site_guest_return_does_not_overwrite_browser_cookies(self):
        for name in ("sid", "full_name", "user_id", "user_image", "system_user"):
            self.cookie_manager.set_cookie(name, "Guest")
        self.cookie_manager.set_cookie("unrelated", "keep")
        self.cookie_manager.to_delete = ["sid", "user_id", "unrelated-old"]
        self.run_return()
        response = Response(status=302)
        self.cookie_manager.flush_cookies(response)
        cookies = response.headers.getlist("Set-Cookie")
        self.assertFalse(any(cookie.startswith(("sid=", "user_id=", "full_name=", "user_image=", "system_user=")) for cookie in cookies))
        self.assertTrue(any(cookie.startswith("unrelated=") for cookie in cookies))
        self.assertIn("unrelated-old", self.cookie_manager.to_delete)
        redirect = urlparse(self.local.response["location"])
        self.assertEqual(redirect.path, "/login")
        self.assertEqual(parse_qs(redirect.query)["redirect-to"], [self.order.failed_url])
        self.assert_no_unsigned_payment_or_login()

    def test_expired_cookie_keeps_normal_login_and_cookie_expiry(self):
        self.request.cookies = {"sid": "expired-browser-sid"}
        self.cookie_manager.to_delete = ["sid", "user_id"]
        self.run_return()
        self.assertEqual(self.cookie_manager.to_delete, ["sid", "user_id"])
        self.assertTrue(self.local.response["location"].startswith("/login?"))
        self.assert_no_unsigned_payment_or_login()

    def test_missing_or_empty_signature_parts_use_failure_fallback(self):
        for parts in (
            {}, {"signature": ""}, {"signature_algorithm": "HMAC-SHA256"},
            {"signature": "untrusted"}, {"signature": "", "signature_algorithm": ""},
        ):
            with self.subTest(parts=parts):
                self.form.clear()
                self.form.update(order_id="test-order", status_id="21", **parts)
                self.run_return()
                self.assertTrue(self.local.response["location"].startswith("/login?"))
                self.assert_no_unsigned_payment_or_login()

    def test_missing_order_id_is_rejected_before_lookup(self):
        self.form.clear()
        with self.assertRaisesRegex(ValueError, "Order Id is required"):
            self.run_return()
        self.get_doc.assert_not_called()
        self.assert_no_unsigned_payment_or_login()

    def test_valid_signed_success_keeps_existing_sync_and_return(self):
        for user, cookies in (
            ("Guest", {}),
            (self.order.owner, {"sid": "active-browser-sid"}),
            ("Guest", {"sid": "expired-browser-sid"}),
        ):
            with self.subTest(user=user, cookies=cookies):
                self.session.user = user
                self.request.cookies = cookies
                self.form.clear()
                self.form.order_id = "test-order"
                self.sign_return()
                self.sync.reset_mock()
                self.lookup_sid.reset_mock()
                self.login.reset_mock()
                self.run_return()
                self.sync.assert_called_once_with("test-order")
                self.lookup_sid.assert_called_once_with(self.order.owner)
                self.login.assert_called_once()
                self.assertEqual(self.local.response["location"], self.order.success_url)

    def test_valid_signed_failure_keeps_existing_flow(self):
        # Routing signed failures differently is deliberately a separate release.
        self.sign_return("27")
        self.run_return()
        self.sync.assert_called_once_with("test-order")
        self.assertEqual(self.local.response["location"], self.order.success_url)

    def test_invalid_signature_is_rejected_without_sync_or_session_resume(self):
        self.sign_return()
        self.form.signature = "invalid"
        with self.assertRaisesRegex(ValueError, "Signature verification failed"):
            self.run_return()
        self.sync.assert_not_called()
        self.lookup_sid.assert_not_called()
        self.login.assert_not_called()

    def test_missing_failure_url_uses_site_home(self):
        self.session.user = self.order.owner
        self.order.failed_url = None
        self.run_return()
        self.assertEqual(self.local.response["location"], "https://example.invalid")
        self.assert_no_unsigned_payment_or_login()
