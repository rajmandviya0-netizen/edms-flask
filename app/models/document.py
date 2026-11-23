from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


# --------------------------------------------------
# FOLDER MODEL
# --------------------------------------------------

class Folder(db.Model):
    __tablename__ = "folder"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(120),
        nullable=False
    )

    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("folder.id"),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=utcnow,
        nullable=False
    )

    parent = db.relationship(
        "Folder",
        remote_side=[id],
        backref=db.backref(
            "subfolders",
            lazy="select"
        )
    )

    documents = db.relationship(
        "Document",
        back_populates="folder",
        lazy="select"
    )


# --------------------------------------------------
# DOCUMENT MODEL
# --------------------------------------------------

class Document(db.Model):
    __tablename__ = "document"

    id = db.Column(
        db.String(36),
        primary_key=True
    )

    name = db.Column(
        db.String(255),
        nullable=False
    )

    folder_id = db.Column(
        db.Integer,
        db.ForeignKey("folder.id"),
        nullable=True
    )

    document_type = db.Column(db.String(100))
    department = db.Column(db.String(100))
    reference_number = db.Column(db.String(100))
    description = db.Column(db.Text)

    status = db.Column(
        db.String(50),
        default="Active"
    )

    retention_date = db.Column(db.Date)
    legal_hold = db.Column(
        db.Boolean,
        default=False
    )

    created_by = db.Column(db.String(120))

    created_at = db.Column(
        db.DateTime,
        default=utcnow
    )

    folder = db.relationship(
        "Folder",
        back_populates="documents"
    )

    versions = db.relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number"
    )


# --------------------------------------------------
# DOCUMENT VERSION MODEL
# --------------------------------------------------

class DocumentVersion(db.Model):
    __tablename__ = "document_version"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    document_id = db.Column(
        db.String(36),
        db.ForeignKey("document.id"),
        nullable=False
    )

    version_number = db.Column(
        db.Integer,
        nullable=False
    )

    stored_name = db.Column(
        db.String(255),
        nullable=False
    )

    size = db.Column(db.Integer)
    sha256 = db.Column(db.String(64))
    uploaded_by = db.Column(db.String(120))

    uploaded_at = db.Column(
        db.DateTime,
        default=utcnow
    )

    document = db.relationship(
        "Document",
        back_populates="versions"
    )


# --------------------------------------------------
# AUDIT LOG MODEL
# --------------------------------------------------

class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # Maps Python username to existing SQLite column "user"
    username = db.Column(
        "user",
        db.String(80)
    )

    action = db.Column(
        db.String(40),
        nullable=False
    )

    document_id = db.Column(
        db.String(36)
    )

    detail = db.Column(db.Text)

    ip_address = db.Column(
        db.String(45)
    )

    # Maps Python created_at to existing SQLite column "timestamp"
    created_at = db.Column(
        "timestamp",
        db.DateTime,
        default=utcnow
    )