"""Search, filter and sort the complaints list for the admin dashboard.

The dashboard and the CSV download both use this, so what staff see on screen
is exactly what they export.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, or_

from models import db
from models.complaint import PRIORITIES, Complaint
from models.team import Team
from models.user import User

NO_TEAM = "__none__"  # filter value meaning "not assigned to any team yet"
MAX_SEARCH_LENGTH = 100
SORTS = {
    "newest": "Newest first",
    "oldest": "Oldest first",
    "priority": "Highest priority first",
}
CSV_COLUMNS = [
    "Complaint ID", "Submitted (UTC)", "Category", "Priority", "Status", "Assigned team",
    "Location", "Latitude", "Longitude", "AI prediction", "AI confidence", "Description",
]


def _clean_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def active_filters(args, valid_statuses, valid_categories) -> dict:
    """Pick the usable filters out of the query string. Anything empty or not
    recognised is dropped, so links built from this are always clean."""
    filters = {}

    text = (args.get("q") or "").strip()[:MAX_SEARCH_LENGTH]
    if text:
        filters["q"] = text

    if args.get("status") in valid_statuses:
        filters["status"] = args["status"]
    if args.get("category") in valid_categories:
        filters["category"] = args["category"]
    if args.get("priority") in PRIORITIES:
        filters["priority"] = args["priority"]

    team = (args.get("team") or "").strip()[:120]
    if team:
        filters["team"] = team

    for key in ("date_from", "date_to"):
        value = _clean_date(args.get(key))
        if value:
            filters[key] = value

    if args.get("sort") in SORTS and args["sort"] != "newest":
        filters["sort"] = args["sort"]

    return filters


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filtered_query(filters: dict):
    query = Complaint.query

    if "q" in filters:
        like = f"%{_escape_like(filters['q'])}%"
        query = query.join(User, Complaint.user_id == User.id).filter(or_(
            Complaint.complaint_id.ilike(like, escape="\\"),
            Complaint.location_name.ilike(like, escape="\\"),
            Complaint.description.ilike(like, escape="\\"),
            User.name.ilike(like, escape="\\"),
            User.email.ilike(like, escape="\\"),
        ))

    if "status" in filters:
        query = query.filter(Complaint.status == filters["status"])
    if "category" in filters:
        query = query.filter(Complaint.damage_category == filters["category"])
    if "priority" in filters:
        query = query.filter(Complaint.priority == filters["priority"])

    if "team" in filters:
        if filters["team"] == NO_TEAM:
            query = query.filter(Complaint.assigned_team.is_(None))
        else:
            query = query.filter(Complaint.assigned_team == filters["team"])

    if "date_from" in filters:
        query = query.filter(Complaint.created_at >= datetime.strptime(filters["date_from"], "%Y-%m-%d"))
    if "date_to" in filters:
        # inclusive of the whole "to" day
        end = datetime.strptime(filters["date_to"], "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Complaint.created_at < end)

    sort = filters.get("sort", "newest")
    if sort == "oldest":
        return query.order_by(Complaint.created_at.asc())
    if sort == "priority":
        rank = db.case(
            (Complaint.priority == "Urgent", 0),
            (Complaint.priority == "High", 1),
            (Complaint.priority == "Normal", 2),
            else_=3,
        )
        return query.order_by(rank, Complaint.created_at.desc())
    return query.order_by(Complaint.created_at.desc())


def team_filter_options() -> list:
    """Team names for the filter dropdown: the current teams plus any name
    already used on a complaint, so older complaints stay filterable."""
    names = {t.name for t in Team.query.all()}
    names.update(r[0] for r in db.session.query(Complaint.assigned_team)
                 .filter(Complaint.assigned_team.isnot(None)).distinct().all())
    return sorted(names, key=str.lower)


def _csv_safe(value):
    """Stop spreadsheet programs treating text as a formula (CSV injection)."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def csv_row(c: Complaint) -> list:
    confidence = f"{c.ai_confidence * 100:.1f}%" if c.ai_confidence is not None else ""
    return [_csv_safe(v) for v in (
        c.complaint_id,
        c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
        c.damage_category,
        c.priority or "Normal",
        c.status,
        c.assigned_team or "",
        c.location_name,
        c.latitude if c.latitude is not None else "",
        c.longitude if c.longitude is not None else "",
        c.ai_prediction or "",
        confidence,
        " ".join((c.description or "").split()),
    )]