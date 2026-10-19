from datetime import datetime
from types import SimpleNamespace

from services import pdf_report


def test_generated_stamp_is_shown_in_ist(monkeypatch):
    monkeypatch.setattr(pdf_report, "utc_now", lambda: datetime(2026, 10, 15, 12, 0))
    assert pdf_report._generated_stamp() == "15 Oct 2026, 05:30 PM IST"


def test_complaint_pdf_builds_with_ist_times():
    created = datetime(2026, 10, 15, 12, 0)
    complaint = SimpleNamespace(
        complaint_id="RR-ABCD1234",
        damage_category="Pothole",
        status="Under Review",
        location_name="MG Road",
        created_at=created,
        updated_at=created,
        assigned_team=None,
        description="A deep hole near the junction.",
        ai_prediction=None,
        updates=[SimpleNamespace(created_at=created, new_status="Submitted", remarks="Complaint submitted by citizen.")],
    )
    buffer = pdf_report.build_complaint_pdf(complaint)
    assert buffer.read(4) == b"%PDF"