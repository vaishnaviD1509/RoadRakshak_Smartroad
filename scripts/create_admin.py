"""Create an administrator account, or promote an existing user to admin.

There is deliberately no admin sign-up page: anyone can register through
the website, but only someone with access to this project's files can make
an admin.

Usage (from the project root):
    python scripts/create_admin.py --email you@example.com
    python scripts/create_admin.py --email you@example.com --name "Your Name"

If the email already has an account, it is promoted to admin and keeps its
current password. Otherwise you'll be prompted for a password (it isn't
echoed and never appears in your shell history).
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from models.user import User  # noqa: E402
from services.user_service import EMAIL_RE, create_or_promote_admin  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", help="Needed only when creating a brand-new account")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        email = args.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise SystemExit("Enter a valid email address.")
        name = args.name
        password = None

        if User.query.filter_by(email=email).first() is None:
            if not name:
                name = input("Full name: ").strip()
            password = getpass.getpass("Password (min 8 characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords do not match.")

        try:
            user, created = create_or_promote_admin(email, name=name, password=password)
        except ValueError as exc:
            raise SystemExit(str(exc))

        if created:
            print(f"Created admin account for {user.email}.")
        else:
            print(f"{user.email} is now an admin (existing password unchanged).")
        print("Log in through the website - admins are taken straight to /admin.")


if __name__ == "__main__":
    main()