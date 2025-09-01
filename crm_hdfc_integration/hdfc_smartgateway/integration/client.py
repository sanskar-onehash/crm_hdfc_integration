import requests

from base64 import b64encode
from crm_hdfc_integration.hdfc_smartgateway.integration import auth


def get_auth_headers(customer_id=None):
    auth_values = auth.get_auth_details()
    headers = {
        "x-merchantid": auth_values.merchant_id,
        "Authorization": f"Basic {b64encode(auth_values.api_key)}",
    }

    if customer_id:
        headers["x-customerid"] = customer_id

    return headers


def prepare_headers(headers=None, customer_id=None, auth=True):
    if not headers:
        headers = {"Content-Type": "application/json"}
    if auth:
        headers.update(get_auth_headers(customer_id))
    return headers


def prepare_url(endpoint):
    return auth.get_base_uri() + endpoint


def make_get_request(
    endpoint,
    customer_id=None,
    auth=True,
    headers=None,
    params=None,
    data=None,
    json=None,
    full_url=None,
    as_json=True,
):
    headers = prepare_headers(headers, customer_id, auth)
    url = full_url if full_url else prepare_url(endpoint)

    res = requests.get(
        url,
        headers=headers,
        params=params,
        data=data,
        json=json,
    )
    res.raise_for_status()

    if as_json:
        return res.json()
    return res.text


def make_post_request(
    endpoint,
    customer_id=None,
    auth=True,
    headers=None,
    params=None,
    data=None,
    json=None,
    full_url=None,
    as_json=True,
):
    headers = prepare_headers(headers, customer_id, auth)
    url = full_url if full_url else prepare_url(endpoint)

    res = requests.post(
        url,
        headers=headers,
        params=params,
        data=data,
        json=json,
    )
    res.raise_for_status()

    if as_json:
        return res.json()
    return res.text


def make_patch_request(
    endpoint,
    customer_id=None,
    auth=True,
    headers=None,
    params=None,
    data=None,
    json=None,
    full_url=None,
    as_json=True,
):
    headers = prepare_headers(headers, customer_id, auth)
    url = full_url if full_url else prepare_url(endpoint)

    res = requests.patch(
        url,
        headers=headers,
        params=params,
        data=data,
        json=json,
    )
    res.raise_for_status()

    if as_json:
        return res.json()
    return res.text


def make_delete_request(
    endpoint,
    customer_id=None,
    auth=True,
    headers=None,
    params=None,
    data=None,
    json=None,
    full_url=None,
    as_json=True,
):
    headers = prepare_headers(headers, customer_id, auth)
    url = full_url if full_url else prepare_url(endpoint)

    res = requests.delete(
        url,
        headers=headers,
        params=params,
        data=data,
        json=json,
    )
    res.raise_for_status()

    if as_json:
        return res.json()
    return res.text
