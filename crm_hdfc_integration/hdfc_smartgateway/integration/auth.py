from crm_hdfc_integration.hdfc_smartgateway.integration import utils


def get_auth_details():
    smartgateway_settings = utils.get_smartgateway_settings()
    return {
        "merchant_id": smartgateway_settings.merchant_id,
        "api_key": smartgateway_settings.get_password("api_key"),
    }


def get_base_uri():
    smartgateway_settings = utils.get_smartgateway_settings()
    return smartgateway_settings.api_base_uri
