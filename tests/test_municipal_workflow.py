"""Municipal staff tools: repair teams, priority, duplicate reports,
search and filters, and the CSV download."""
import csv
import io
import re
from datetime import datetime

import pytest

from models import db
from models.complaint import Complaint
from models.complaint_update import ComplaintUpdate
from models.team import Team
from models.user import User
from services.duplicate_service import distance_meters
from services.team_service import team_summaries

BASE_LAT, BASE_LNG = 17.3300, 76.8300


def _make_user(app, email, role="citizen", name="Some User"):
    with app.app_context():
        user = User(name=name, email=email, role=role)
        user.set_password("longenough1")
        db.session.add(user)
        db.session.commit()
        return user.id


def _sign_in(client, app, email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        ident = (user.id, user.name, user.role)
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"], sess["role"] = ident


def _complaint(app, owner_email="citizen@example.com", location="MG Road", **extra):
    extra.setdefault("damage_category", "Pothole")
    extra.setdefault("description", "Seeded for municipal tests.")
    with app.app_context():
        owner = User.query.filter_by(email=owner_email).first()
        c = Complaint(user_id=owner.id, location_name=location, **extra)
        db.session.add(c)
        db.session.commit()
        return c.complaint_id


def _get(app, cid):
    with app.app_context():
        return Complaint.query.filter_by(complaint_id=cid).first()


def _add_team(app, name, active=True):
    with app.app_context():
        db.session.add(Team(name=name, is_active=active))
        db.session.commit()


@pytest.fixture
def staff(app, client):
    """A signed-in administrator and one citizen who owns the complaints."""
    _make_user(app, "admin@example.com", role="admin", name="Admin Person")
    _make_user(app, "citizen@example.com", name="Citizen Person")
    _sign_in(client, app, "admin@example.com")


def _flash_text(client, path="/admin/teams"):
    return client.get(path).data.decode()


# --- Repair teams ------------------------------------------------------

def test_teams_page_needs_an_admin(app, client):
    _make_user(app, "citizen@example.com")
    _sign_in(client, app, "citizen@example.com")
    assert client.get("/admin/teams").status_code == 302
    assert client.post("/admin/teams/add", data={"name": "X Team"}).status_code == 302


def test_admin_can_add_a_team(app, client, staff):
    client.post("/admin/teams/add", data={"name": "  Roads   Maintenance  Ward 12 "}, follow_redirects=True)
    with app.app_context():
        assert [t.name for t in Team.query.all()] == ["Roads Maintenance Ward 12"]
    assert "Roads Maintenance Ward 12" in _flash_text(client)


def test_team_names_are_checked(app, client, staff):
    _add_team(app, "Night Crew")
    for bad in ["", "A", "x" * 121, "night crew", "NIGHT CREW"]:
        client.post("/admin/teams/add", data={"name": bad})
    with app.app_context():
        assert Team.query.count() == 1


def test_adding_a_switched_off_team_turns_it_back_on(app, client, staff):
    _add_team(app, "Night Crew", active=False)
    client.post("/admin/teams/add", data={"name": "night crew"})
    with app.app_context():
        team = Team.query.one()
        assert team.name == "Night Crew" and team.is_active is True


def test_team_can_be_switched_off_and_on(app, client, staff):
    _add_team(app, "Night Crew")
    with app.app_context():
        team_id = Team.query.one().id
    client.post(f"/admin/teams/{team_id}/active", data={"active": "0"})
    with app.app_context():
        assert Team.query.one().is_active is False
    client.post(f"/admin/teams/{team_id}/active", data={"active": "1"})
    with app.app_context():
        assert Team.query.one().is_active is True
    assert client.post("/admin/teams/9999/active", data={"active": "1"}).status_code == 302


def test_complaint_page_uses_a_dropdown_once_teams_exist(app, client, staff):
    cid = _complaint(app)
    page = client.get(f"/admin/complaints/{cid}").data.decode()
    assert '<input type="text" class="form-control" id="assigned_team"' in page

    _add_team(app, "Ward 12 Roads")
    _add_team(app, "Switched Off Crew", active=False)
    page = client.get(f"/admin/complaints/{cid}").data.decode()
    assert '<select class="form-select" id="assigned_team"' in page
    assert "Ward 12 Roads" in page
    assert "Switched Off Crew" not in page


def test_only_listed_teams_can_be_assigned_once_teams_exist(app, client, staff):
    _add_team(app, "Ward 12 Roads")
    cid = _complaint(app)

    client.post(f"/admin/complaints/{cid}/status",
                data={"status": "Verified", "assigned_team": "Typed Freehand", "remarks": ""})
    assert _get(app, cid).assigned_team is None

    client.post(f"/admin/complaints/{cid}/status",
                data={"status": "Assigned for Repair", "assigned_team": "Ward 12 Roads", "remarks": ""})
    c = _get(app, cid)
    assert (c.status, c.assigned_team) == ("Assigned for Repair", "Ward 12 Roads")


def test_an_older_typed_team_is_kept_when_other_changes_are_saved(app, client, staff):
    cid = _complaint(app, status="Verified", assigned_team="Old Typed Team")
    _add_team(app, "Ward 12 Roads")

    page = client.get(f"/admin/complaints/{cid}").data.decode()
    assert "Old Typed Team" in page  # still selectable

    client.post(f"/admin/complaints/{cid}/status",
                data={"status": "Verified", "assigned_team": "Old Typed Team", "remarks": "Called the ward office."})
    assert _get(app, cid).assigned_team == "Old Typed Team"


def test_team_workload_counts(app, client, staff):
    _add_team(app, "Ward 12 Roads")
    _complaint(app, location="A", status="Assigned for Repair", assigned_team="Ward 12 Roads")
    _complaint(app, location="B", status="Repair in Progress", assigned_team="Ward 12 Roads")
    _complaint(app, location="C", status="Resolved", assigned_team="Ward 12 Roads")
    _complaint(app, location="D", status="Verified")

    with app.app_context():
        [row] = team_summaries()
    assert (row["working"], row["resolved"], row["total"]) == (2, 1, 3)
    assert "Ward 12 Roads" in client.get("/admin/teams").data.decode()


def test_team_names_used_before_can_be_added_in_one_click(app, client, staff):
    _complaint(app, status="Verified", assigned_team="Typed Earlier")
    page = client.get("/admin/teams").data.decode()
    assert 'id="unlisted"' in page and "Typed Earlier" in page

    client.post("/admin/teams/add", data={"name": "Typed Earlier"})
    assert 'id="unlisted"' not in client.get("/admin/teams").data.decode()


# --- Priority ----------------------------------------------------------

def test_new_complaints_start_at_normal_priority(app, staff):
    assert _get(app, _complaint(app)).priority == "Normal"


def test_admin_can_change_priority_and_it_is_logged(app, client, staff):
    cid = _complaint(app)
    client.post(f"/admin/complaints/{cid}/priority", data={"priority": "Urgent"})

    c = _get(app, cid)
    assert c.priority == "Urgent"
    with app.app_context():
        log = ComplaintUpdate.query.filter_by(complaint_id=c.id).order_by(ComplaintUpdate.id.desc()).first()
        assert log.remarks == "Priority changed from Normal to Urgent."
        assert log.previous_status == log.new_status == "Submitted"
        assert log.updated_by is not None


def test_bad_or_unchanged_priority_is_refused(app, client, staff):
    cid = _complaint(app)
    client.post(f"/admin/complaints/{cid}/priority", data={"priority": "Whenever"})
    client.post(f"/admin/complaints/{cid}/priority", data={"priority": "Normal"})
    c = _get(app, cid)
    assert c.priority == "Normal"
    with app.app_context():
        assert ComplaintUpdate.query.filter_by(complaint_id=c.id).count() == 0


def test_citizen_cannot_change_priority(app, client, staff):
    cid = _complaint(app)
    _sign_in(client, app, "citizen@example.com")
    client.post(f"/admin/complaints/{cid}/priority", data={"priority": "Urgent"})
    assert _get(app, cid).priority == "Normal"


def test_dashboard_can_sort_by_priority(app, client, staff):
    ids = {p: _complaint(app, location=f"{p} Road", priority=p) for p in ("Low", "Urgent", "Normal", "High")}
    html = client.get("/admin/?sort=priority").data.decode()
    order = sorted(ids, key=lambda p: html.index(ids[p]))
    assert order == ["Urgent", "High", "Normal", "Low"]


def test_urgent_and_high_open_card_ignores_closed_complaints(app, client, staff):
    _complaint(app, location="a", priority="Urgent")
    _complaint(app, location="b", priority="High", status="Verified")
    _complaint(app, location="c", priority="Urgent", status="Resolved")
    _complaint(app, location="d", priority="Normal")
    html = client.get("/admin/").data.decode()
    chunk = html[:html.index("High or urgent, still open")]
    number = int(re.findall(r'rr-stat-number">(\d+)<', chunk)[-1])
    assert number == 2


# --- Possible duplicates -------------------------------------------------

def test_distance_helper_is_sensible():
    assert distance_meters(BASE_LAT, BASE_LNG, BASE_LAT, BASE_LNG) == pytest.approx(0, abs=0.01)
    assert distance_meters(BASE_LAT, BASE_LNG, BASE_LAT + 0.001, BASE_LNG) == pytest.approx(111, abs=2)


def test_nearby_open_complaints_are_listed_as_possible_duplicates(app, client, staff):
    mine = _complaint(app, location="Mine", latitude=BASE_LAT, longitude=BASE_LNG)
    near = _complaint(app, location="Next door", latitude=BASE_LAT + 0.0002, longitude=BASE_LNG)
    _complaint(app, location="Far away", latitude=BASE_LAT + 0.002, longitude=BASE_LNG)
    _complaint(app, location="Fixed already", latitude=BASE_LAT, longitude=BASE_LNG, status="Resolved")
    _complaint(app, location="Thrown out", latitude=BASE_LAT, longitude=BASE_LNG, status="Rejected")

    page = client.get(f"/admin/complaints/{mine}").data.decode()
    section = page[page.index('id="duplicates"'):page.index("History")]
    assert near in section
    assert "Next door" in section and "m away" in section
    for left_out in ("Far away", "Fixed already", "Thrown out"):
        assert left_out not in section


def test_same_category_duplicates_come_first(app, client, staff):
    mine = _complaint(app, latitude=BASE_LAT, longitude=BASE_LNG)
    other_kind = _complaint(app, location="Cracks", damage_category="Road Cracks",
                            latitude=BASE_LAT + 0.00005, longitude=BASE_LNG)
    same_kind = _complaint(app, location="Pothole too", latitude=BASE_LAT + 0.0003, longitude=BASE_LNG)

    page = client.get(f"/admin/complaints/{mine}").data.decode()
    assert page.index(same_kind) < page.index(other_kind)


def test_complaint_without_a_pin_explains_why_no_duplicates_are_shown(app, client, staff):
    cid = _complaint(app, latitude=None, longitude=None)
    assert "no map location" in client.get(f"/admin/complaints/{cid}").data.decode()


def test_marking_a_duplicate_rejects_it_with_a_reason_the_citizen_can_see(app, client, staff):
    original = _complaint(app, location="Original", latitude=BASE_LAT, longitude=BASE_LNG)
    copy = _complaint(app, location="Copy", latitude=BASE_LAT, longitude=BASE_LNG)

    client.post(f"/admin/complaints/{copy}/duplicate", data={"original_id": original})
    c = _get(app, copy)
    assert c.status == "Rejected"

    _sign_in(client, app, "citizen@example.com")
    page = client.get(f"/track?complaint_id={copy}").data.decode()
    assert f"Duplicate of {original}" in page


def test_duplicate_marking_refuses_bad_requests(app, client, staff):
    a = _complaint(app, location="A")
    done = _complaint(app, location="B", status="Resolved")
    other = _complaint(app, location="C")

    client.post(f"/admin/complaints/{a}/duplicate", data={"original_id": a})           # itself
    client.post(f"/admin/complaints/{a}/duplicate", data={"original_id": "RR-NOPE"})   # unknown
    client.post(f"/admin/complaints/{done}/duplicate", data={"original_id": other})    # resolved
    assert _get(app, a).status == "Submitted"
    assert _get(app, done).status == "Resolved"


# --- Search and filters --------------------------------------------------

def test_search_finds_by_id_place_description_and_reporter(app, client, staff):
    _make_user(app, "ravi@example.com", name="Ravi Kumar")
    by_place = _complaint(app, location="Station Road")
    by_text = _complaint(app, location="Elsewhere", description="Water collects near the temple gate")
    by_reporter = _complaint(app, owner_email="ravi@example.com", location="Somewhere else")

    def ids_for(term):
        html = client.get("/admin/", query_string={"q": term}).data.decode()
        return set(re.findall(r'<td class="rr-complaint-id">(RR-[0-9A-F]{8})</td>', html))

    assert ids_for("station") == {by_place}
    assert ids_for("TEMPLE gate") == {by_text}
    assert ids_for("ravi kumar") == {by_reporter}
    assert ids_for("ravi@example") == {by_reporter}
    assert ids_for(by_place.lower()) == {by_place}
    assert ids_for("zzz-nothing") == set()


def test_search_treats_percent_and_underscore_as_plain_text(app, client, staff):
    _complaint(app, location="Plain Road")
    _complaint(app, location="100% flooded")
    html = client.get("/admin/", query_string={"q": "%"}).data.decode()
    assert "100% flooded" in html and "Plain Road" not in html
    html = client.get("/admin/", query_string={"q": "_"}).data.decode()
    assert "Plain Road" not in html


def test_filters_by_category_priority_and_team(app, client, staff):
    pothole = _complaint(app, location="P", priority="High", assigned_team="Ward 12 Roads", status="Verified")
    cracks = _complaint(app, location="C", damage_category="Road Cracks")

    def ids(**params):
        html = client.get("/admin/", query_string=params).data.decode()
        return set(re.findall(r'<td class="rr-complaint-id">(RR-[0-9A-F]{8})</td>', html))

    assert ids(category="Road Cracks") == {cracks}
    assert ids(priority="High") == {pothole}
    assert ids(team="Ward 12 Roads") == {pothole}
    assert ids(team="__none__") == {cracks}
    assert ids(category="Pothole", priority="High", team="Ward 12 Roads") == {pothole}
    assert ids(category="Road Cracks", priority="High") == set()


def test_filters_by_date_range_including_the_end_day(app, client, staff):
    old = _complaint(app, location="Old", created_at=datetime(2026, 1, 10, 9, 0))
    edge = _complaint(app, location="Edge", created_at=datetime(2026, 2, 1, 23, 30))
    late = _complaint(app, location="Late", created_at=datetime(2026, 3, 5, 9, 0))

    def ids(**params):
        html = client.get("/admin/", query_string=params).data.decode()
        return set(re.findall(r'<td class="rr-complaint-id">(RR-[0-9A-F]{8})</td>', html))

    assert ids(date_from="2026-02-01", date_to="2026-02-01") == {edge}
    assert ids(date_to="2026-02-01") == {old, edge}
    assert ids(date_from="2026-02-02") == {late}


def test_unrecognised_filter_values_are_ignored(app, client, staff):
    cid = _complaint(app)
    html = client.get("/admin/", query_string={
        "status": "Banana", "category": "Nope", "priority": "Whenever", "sort": "sideways",
        "date_from": "not-a-date",
    }).data.decode()
    assert cid in html


def test_page_links_keep_the_filters(app, client, staff):
    for i in range(16):
        _complaint(app, location=f"Bulk {i}")
    _complaint(app, location="Cracked", damage_category="Road Cracks")

    html = client.get("/admin/", query_string={"category": "Pothole"}).data.decode()
    older = re.search(r'href="([^"]+)">Older', html).group(1)
    assert "category=Pothole" in older and "page=2" in older
    assert "Page 1 of 2" in html


def test_empty_search_result_offers_to_clear_filters(app, client, staff):
    html = client.get("/admin/", query_string={"q": "nothing matches this"}).data.decode()
    assert "No complaints match these filters" in html


# --- CSV download ---------------------------------------------------------

def _csv_rows(response):
    text = response.data.decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


def test_csv_download_has_a_header_and_one_row_per_complaint(app, client, staff):
    _complaint(app, location="Station Road", priority="High", ai_prediction="Pothole", ai_confidence=0.87,
               latitude=BASE_LAT, longitude=BASE_LNG)
    resp = client.get("/admin/export.csv")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "road-rakshak-complaints-" in resp.headers["Content-Disposition"]
    header, row = _csv_rows(resp)
    assert header[:5] == ["Complaint ID", "Submitted (UTC)", "Category", "Priority", "Status"]
    assert row[3] == "High" and row[6] == "Station Road" and row[10] == "87.0%"


def test_csv_follows_the_dashboard_filters(app, client, staff):
    _complaint(app, location="Keep", priority="Urgent")
    _complaint(app, location="Skip", priority="Low")
    rows = _csv_rows(client.get("/admin/export.csv", query_string={"priority": "Urgent"}))
    assert [r[6] for r in rows[1:]] == ["Keep"]


def test_csv_cells_cannot_run_as_spreadsheet_formulas(app, client, staff):
    _complaint(app, location='=HYPERLINK("http://evil.example","click")', description="+SUM(A1)")
    _, row = _csv_rows(client.get("/admin/export.csv"))
    assert row[6].startswith("'=") and row[11].startswith("'+")


def test_csv_needs_an_admin(app, client):
    assert client.get("/admin/export.csv").status_code == 302
    _make_user(app, "citizen@example.com")
    _sign_in(client, app, "citizen@example.com")
    assert client.get("/admin/export.csv").status_code == 302