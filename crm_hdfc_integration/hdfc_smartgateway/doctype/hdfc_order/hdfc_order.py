# Copyright (c) 2025, OneHash and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import crm_hdfc_integration.hdfc_smartgateway.integration.service as service


class HDFCOrder(Document):

    def autoname(self):
        self.name = service.generate_order_id()
