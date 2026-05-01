from datetime import datetime, timezone
from zoneinfo import ZoneInfo


PHILIPPINE_TIMEZONE = ZoneInfo('Asia/Manila')
UTC = timezone.utc


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


def ph_now():
    return datetime.now(PHILIPPINE_TIMEZONE)


def ph_today():
    return ph_now().date()


def ph_year():
    return ph_now().year


def serialize_utc_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.astimezone(PHILIPPINE_TIMEZONE).isoformat(timespec='seconds')


def serialize_ph_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=PHILIPPINE_TIMEZONE)
    else:
        value = value.astimezone(PHILIPPINE_TIMEZONE)
    return value.isoformat(timespec='seconds')
