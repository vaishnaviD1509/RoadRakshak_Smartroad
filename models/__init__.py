from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import models so they register with SQLAlchemy's metadata when
# models package is imported (e.g. before db.create_all()).
from models.user import User  # noqa: E402,F401
from models.complaint import Complaint  # noqa: E402,F401
from models.complaint_update import ComplaintUpdate  # noqa: E402,F401
from models.repair_evidence import RepairEvidence  # noqa: E402,F401