"""Route-protection decorators shared across blueprints.

login_required sends anonymous visitors to the citizen login.
admin_required sends anonymous visitors to the municipal login, so staff
pages never point people at the citizen page. It also re-checks the account
in the database on every request, so removing someone's admin access takes
effect immediately instead of when they next log out.
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request

from models import db
from models.user import User


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.municipal_login", next=request.path))
        if session.get("role") != "admin":
            flash("You don't have permission to view that page.", "danger")
            return redirect(url_for("main.index"))

        user = db.session.get(User, session["user_id"])
        if user is None or not user.is_admin:
            session.clear()
            flash("Your staff access has changed. Please log in again.", "warning")
            return redirect(url_for("auth.municipal_login"))
        return view_func(*args, **kwargs)
    return wrapped