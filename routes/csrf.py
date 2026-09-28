"""Minimal CSRF protection (no extra dependency).

A per-session token is generated once, exposed to every template via a
context processor, and checked on state-changing POST requests. This is
enough to stop a cross-site form submission, since an attacker's page
cannot read the victim's session-bound token.
"""
import secrets
from flask import session, abort, request


def get_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def validate_csrf(form) -> None:
    token = form.get("csrf_token", "")
    if not token or token != session.get("_csrf_token"):
        abort(400, description="Invalid or missing CSRF token.")


def register_csrf(app):
    app.jinja_env.globals["csrf_token"] = get_csrf_token

    @app.before_request
    def _check_csrf():
        if app.config.get("TESTING"):
            return
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            validate_csrf(request.form)


# --- One-time submission tokens ---------------------------------------
# Separate from the CSRF token (which stays constant for the session).
# A fresh one-time token is minted every time the report form is
# rendered and is consumed (removed from the session) the moment a POST
# uses it - so a duplicate submission caused by double-clicking Submit,
# or by the browser resubmitting via Back, is rejected rather than
# creating a second complaint.

def get_form_token(name: str) -> str:
    key = f"_form_token_{name}"
    token = secrets.token_hex(16)
    session[key] = token
    return token


def consume_form_token(name: str, submitted_token: str) -> bool:
    key = f"_form_token_{name}"
    expected = session.pop(key, None)
    return bool(expected) and bool(submitted_token) and secrets.compare_digest(expected, submitted_token)