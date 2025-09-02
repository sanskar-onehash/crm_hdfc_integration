import frappe
from base64 import b64encode
from frappe import utils
from pytz import timezone


def parse_utc_datetime(datetime_like_obj):
    system_tz_name = utils.get_system_timezone()
    system_tz = timezone(system_tz_name)

    datetime = utils.get_datetime(datetime_like_obj)
    if datetime:
        return datetime.astimezone(system_tz).replace(tzinfo=None)
    return None


def get_base64_string(string: str):
    return b64encode(string.encode("utf-8")).decode("utf-8")


def get_or_throw(object, key):
    value = object.get(key)
    if not value:
        frappe.throw(f"{key} not found")
    return value


def ensure_parsed(value: list | dict | str | None) -> list | dict | None:
    if isinstance(value, str):
        return frappe.json.loads(value)
    return value
