"""Time helpers: the database stores UTC, people read Indian Standard Time.

Times are stored as naive UTC datetimes (that is what SQLite keeps). Thesec
helpers replace the deprecated datetime.utcnow() / utcfromtimestamp() and
convert to IST for display.
"""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def utc_now() -> datetime:
    """The current UTC time as a naive datetime (the style the database stores)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_from_timestamp(timestamp: float) -> datetime:
    """A naive UTC datetime from a Unix timestamp (e.g. a file's modified time)."""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)


def to_ist(value):
    """Convert a datetime to IST. A naive datetime is taken to be UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def format_ist(value, fmt: str = "%d %b %Y, %I:%M %p") -> str:
    """Format a datetime in IST for display, e.g. '15 Oct 2026, 05:30 PM IST'.

    The ' IST' label is added only when the format shows a time of day.
    Use it in templates as {{ value|ist }} or {{ value|ist('%d %b %Y') }}.
    """
    if value is None:
        return ""
    text = to_ist(value).strftime(fmt)
    if "%H" in fmt or "%I" in fmt:
        text += " IST"
    return text