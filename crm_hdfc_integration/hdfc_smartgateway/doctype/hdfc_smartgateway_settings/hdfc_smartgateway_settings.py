# Copyright (c) 2025, OneHash and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class HDFCSmartGatewaySettings(Document):

    def before_save(self):
        if self.api_base_uri and self.api_base_uri.endswith("/"):
            self.set("api_base_uri", self.api_base_uri[:-1])
