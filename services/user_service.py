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