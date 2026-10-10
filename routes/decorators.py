"""Route-protection decorators shared across blueprints.

login_required sends anonymous visitors to the citizen login.
admin_required sends anonymous visitors to the municipal login, so staff
pages never point people at the citizen page.
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request


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
        return view_func(*args, **kwargs)
    return wrapped