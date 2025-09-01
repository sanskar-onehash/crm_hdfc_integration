from pytz import timezone
from frappe import utils


def parse_utc_datetime(datetime_like_obj):
    system_tz_name = utils.get_system_timezone()
    system_tz = timezone(system_tz_name)

    datetime = utils.get_datetime(datetime_like_obj)
    if datetime:
        return datetime.astimezone(system_tz).replace(tzinfo=None)
    return None
