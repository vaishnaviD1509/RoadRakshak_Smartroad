import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db
from models.user import User

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# One login flow, two portals. Each portal only lets in its own kind of
# account, so citizens and municipal staff never share a login page.
PORTALS = {
    "citizen": {
        "template": "login.html",
        "admin": False,
        "wrong_portal": "This is the citizen login. Municipal staff, please use the municipal login.",
    },
    "municipal": {
        "template": "municipal_login.html",
        "admin": True,
        "wrong_portal": "This is the municipal staff login. Citizens, please use the citizen login.",
    },
}


def _is_safe_next(next_url):
    """Only allow same-site relative paths (blocks '//evil.com' and '\\' tricks)."""
    return (
        bool(next_url)
        and next_url.startswith("/")
        and not next_url.startswith("//")
        and "\\" not in next_url
    )


def _already_logged_in_redirect():
    if session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("main.index"))


def _handle_login(portal_name):
    portal = PORTALS[portal_name]

    if "user_id" in session:
        return _already_logged_in_redirect()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        # Same message for "no such account" and "wrong password".
        if user is None or not user.check_password(password):
            flash("Incorrect email or password.", "danger")
            return render_template(portal["template"], email=email), 401

        # Only after the password is correct do we point the person to the
        # other portal, so this can't be used to discover which emails exist.
        if user.is_admin != portal["admin"]:
            flash(portal["wrong_portal"], "warning")
            return render_template(portal["template"], email=email), 403

        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["role"] = user.role

        flash(f"Welcome back, {user.name}.", "success")

        next_url = request.args.get("next")
        if _is_safe_next(next_url):
            return redirect(next_url)
        if user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.index"))

    return render_template(portal["template"], email="")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        errors = []
        if not name:
            errors.append("Full name is required.")
        if not email or not EMAIL_RE.match(email):
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if email and User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", name=name, email=email), 400

        user = User(name=name, email=email, role="citizen")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html", name="", email="")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Citizen login."""
    return _handle_login("citizen")


@auth_bp.route("/municipal/login", methods=["GET", "POST"])
def municipal_login():
    """Municipal staff (admin) login. There is no sign-up here: staff
    accounts are created with scripts/create_admin.py."""
    return _handle_login("municipal")


@auth_bp.route("/logout")
def logout():
    was_admin = session.get("role") == "admin"
    session.clear()
    flash("You have been logged out.", "success")
    if was_admin:
        return redirect(url_for("auth.municipal_login"))
    return redirect(url_for("main.index"))