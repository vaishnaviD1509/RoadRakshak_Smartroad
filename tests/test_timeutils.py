from datetime import datetime, timezone

from services.timeutils import format_ist, to_ist, utc_from_timestamp, utc_now


def test_utc_now_is_a_naive_utc_datetime():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    value = utc_now()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert value.tzinfo is None
    assert before <= value <= after


def test_utc_from_timestamp_is_naive_utc():
    assert utc_from_timestamp(0) == datetime(1970, 1, 1, 0, 0, 0)


def test_to_ist_adds_five_hours_thirty_minutes():
    naive = to_ist(datetime(2026, 10, 15, 12, 0))
    aware = to_ist(datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc))
    for result in (naive, aware):
        assert (result.hour, result.minute) == (17, 30)


def test_format_ist_shows_time_and_zone_label():
    assert format_ist(datetime(2026, 10, 15, 12, 0)) == "15 Oct 2026, 05:30 PM IST"


def test_format_ist_date_only_uses_the_ist_day_and_no_label():
    # 20:00 UTC is 01:30 the next day in India.
    assert format_ist(datetime(2026, 10, 15, 20, 0), "%d %b %Y") == "16 Oct 2026"


def test_format_ist_handles_missing_time():
    assert format_ist(None) == ""
    assert to_ist(None) is None


def test_ist_filter_is_available_in_templates(app):
    template = app.jinja_env.from_string("{{ when|ist }}")
    assert template.render(when=datetime(2026, 10, 15, 12, 0)) == "15 Oct 2026, 05:30 PM IST"