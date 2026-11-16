from frappe.tests.utils import FrappeTestCase

from crm_hdfc_integration.hdfc_smartgateway.integration import utils


class TestHDFCCustomerID(FrappeTestCase):
    def test_keeps_existing_safe_customer_id(self):
        customer_id = "Adrien de la POIX de FREMINVILLE"

        self.assertEqual(utils.get_hdfc_customer_id(customer_id), customer_id)

    def test_hashes_non_ascii_customer_id_to_safe_stable_value(self):
        customer_id = "Héloïse de la POIX de FREMINVILLE"

        hdfc_customer_id = utils.get_hdfc_customer_id(customer_id)

        self.assertEqual(hdfc_customer_id, utils.get_hdfc_customer_id(customer_id))
        self.assertTrue(hdfc_customer_id.isascii())
        self.assertTrue(hdfc_customer_id.isalnum())
        self.assertEqual(len(hdfc_customer_id), 32)

    def test_hashes_ascii_customer_id_over_the_limit(self):
        hdfc_customer_id = utils.get_hdfc_customer_id("A" * 33)

        self.assertTrue(hdfc_customer_id.isalnum())
        self.assertEqual(len(hdfc_customer_id), 32)
