"""User account helpers that don't belong to a web request."""
import re

from models import db
from models.user import User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


def create_or_promote_admin(email, name=None, password=None):
    """Make `email` an administrator.

    - If an account with that email already exists, it is promoted and its
      password is left untouched.
    - Otherwise a new admin account is created, which needs a name and a
      password of at least 8 characters.

    Returns (user, created). Raises ValueError with a readable message.
    """
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")

    user = User.query.filter_by(email=email).first()
    if user is not None:
        user.role = "admin"
        db.session.commit()
        return user, False

    name = (name or "").strip()
    if not name:
        raise ValueError("A name is required to create a new admin account.")
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")

    user = User(name=name, email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, True

def list_staff():
    """All municipal (admin) accounts, oldest first."""
    return User.query.filter_by(role="admin").order_by(User.created_at.asc(), User.id.asc()).all()


def remove_admin_access(user_id, acting_admin_id):
    """Turn a staff account back into an ordinary citizen account.

    The account, its complaints and its history are kept; it just can no longer
    use the municipal pages. You cannot remove your own access, and the last
    remaining administrator can never be removed, so the system is never left
    without anyone who can manage it.
    """
    user = db.session.get(User, user_id)
    if user is None or not user.is_admin:
        raise ValueError("That staff account was not found.")
    if user.id == acting_admin_id:
        raise ValueError("You cannot remove your own admin access. Ask another administrator to do it.")
    if User.query.filter_by(role="admin").count() <= 1:
        raise ValueError("At least one administrator must remain.")

    user.role = "citizen"
    db.session.commit()
    return user