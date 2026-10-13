"""Repair teams: the list staff can assign complaints to, and their workload."""
from sqlalchemy import func

from models import db
from models.complaint import Complaint
from models.team import Team
from services.complaint_service import UpdateError

MAX_TEAM_NAME_LENGTH = 120
MIN_TEAM_NAME_LENGTH = 2
WORKING_STATUSES = ("Assigned for Repair", "Repair in Progress")


def active_team_names() -> list:
    rows = Team.query.filter_by(is_active=True).order_by(func.lower(Team.name)).all()
    return [t.name for t in rows]


def create_team(name: str) -> Team:
    name = " ".join((name or "").split())  # trim and collapse spaces
    if len(name) < MIN_TEAM_NAME_LENGTH:
        raise UpdateError("Enter a team name (at least 2 characters).")
    if len(name) > MAX_TEAM_NAME_LENGTH:
        raise UpdateError(f"Team name must be {MAX_TEAM_NAME_LENGTH} characters or fewer.")

    existing = Team.query.filter(func.lower(Team.name) == name.lower()).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()
            return existing
        raise UpdateError(f'A team called "{existing.name}" already exists.')

    team = Team(name=name)
    db.session.add(team)
    db.session.commit()
    return team


def set_team_active(team_id: int, active: bool) -> Team:
    team = db.session.get(Team, team_id)
    if team is None:
        raise UpdateError("That team no longer exists.")
    team.is_active = bool(active)
    db.session.commit()
    return team


def team_summaries() -> list:
    """Every team with how many complaints it is working on, has resolved,
    and has in total. Used by the Teams page."""
    counts = {}
    rows = (
        db.session.query(Complaint.assigned_team, Complaint.status, func.count(Complaint.id))
        .filter(Complaint.assigned_team.isnot(None))
        .group_by(Complaint.assigned_team, Complaint.status)
        .all()
    )
    for team_name, status, n in rows:
        entry = counts.setdefault(team_name, {"working": 0, "resolved": 0, "total": 0})
        entry["total"] += n
        if status in WORKING_STATUSES:
            entry["working"] += n
        elif status == "Resolved":
            entry["resolved"] += n

    result = []
    for team in Team.query.order_by(func.lower(Team.name)).all():
        c = counts.get(team.name, {"working": 0, "resolved": 0, "total": 0})
        result.append({"team": team, **c})
    return result


def unlisted_team_names() -> list:
    """Team names typed into complaints earlier that are not in the teams list
    yet (from before the dropdown existed), so staff can add them in one click."""
    known = {t.name.lower() for t in Team.query.all()}
    used = [r[0] for r in db.session.query(Complaint.assigned_team)
            .filter(Complaint.assigned_team.isnot(None)).distinct().all()]
    return sorted((n for n in used if n.lower() not in known), key=str.lower)