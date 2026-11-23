import hashlib
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    request,
    send_from_directory,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.document import Document, DocumentVersion, AuditLog, Folder
from app.models.user import User


document_bp = Blueprint("documents", __name__)

# --------------------------------------------------
# ACCESS MODE
#   "strict" -> normal users see only documents they uploaded
#   "shared" -> everyone can see and download every document
# Admins always see everything.
# Change this one word, save, and restart the server.
# --------------------------------------------------
ACCESS_MODE = "strict"

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "txt",
    "png", "jpg", "jpeg", "tif", "tiff",
}

ALLOWED_ACTIONS = {
    "UPLOAD",
    "VERSION_UPLOAD",
    "VERSION_DOWNLOAD",
    "VIEW",
    "DOWNLOAD",
    "DELETE",
    "MOVE",
    "LEGAL_HOLD",
    "METADATA_UPDATE",
    "ROLE_CHANGE",
}

EDITABLE_STATUSES = {
    "draft": "Draft",
    "active": "Active",
    "archived": "Archived",
    "pending": "Pending",
}


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def is_admin():
    return getattr(current_user, "role", None) == "Admin"


def current_username():
    return getattr(current_user, "username", None)


def can_see_all():
    return is_admin() or ACCESS_MODE == "shared"


def can_access(document):
    """May the current user see, preview and download this document?"""

    if can_see_all():
        return True

    username = current_username()

    return username is not None and document.created_by == username


def can_modify(document):
    """May the current user edit, move or add versions to it?"""

    if is_admin():
        return True

    username = current_username()

    return username is not None and document.created_by == username


def utcnow():
    return datetime.now(timezone.utc)


def upload_folder():
    configured_folder = current_app.config.get("UPLOAD_FOLDER")

    if configured_folder:
        folder = Path(configured_folder)
    else:
        project_root = Path(__file__).resolve().parents[2]
        folder = project_root / "storage" / "uploads"

    folder.mkdir(parents=True, exist_ok=True)

    return folder


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def validate_file_content(extension, file_bytes):
    signatures = {
        "pdf": file_bytes.startswith(b"%PDF-"),
        "png": file_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpg": file_bytes.startswith(b"\xff\xd8\xff"),
        "jpeg": file_bytes.startswith(b"\xff\xd8\xff"),
        "tif": file_bytes.startswith((b"II*\x00", b"MM\x00*")),
        "tiff": file_bytes.startswith((b"II*\x00", b"MM\x00*")),
    }

    if extension in signatures and not signatures[extension]:
        return False

    return True


def log_action(action, document_id=None, detail=""):
    """
    Create an audit entry using the actual AuditLog model fields.

    AuditLog fields:
    id, username, action, document_id, detail,
    ip_address, created_at
    """

    username = (
        current_username()
        if current_user.is_authenticated
        else None
    )

    entry = AuditLog(
        username=username or "System",
        action=action,
        document_id=(
            str(document_id)
            if document_id is not None
            else None
        ),
        detail=detail,
        ip_address=request.remote_addr,
        created_at=utcnow(),
    )

    db.session.add(entry)


def get_document_or_404(document_id):
    document = db.session.get(Document, document_id)

    # In strict mode a document the user may not see
    # looks exactly like one that does not exist.
    if document is None or not can_access(document):
        abort(404)

    return document


def get_latest_version(document):
    if not document.versions:
        abort(404, description="No file version is available.")

    return max(
        document.versions,
        key=lambda version: version.version_number,
    )


def resolve_folder(raw_value):
    """
    Convert a folder_id value from JSON or FormData into a Folder.

    Returns a tuple: (folder, error_message)

    - None, "", or "null"  -> (None, None)  meaning Unassigned
    - valid existing ID    -> (Folder, None)
    - invalid or missing   -> (None, "error message")
    """

    if raw_value is None:
        return None, None

    if isinstance(raw_value, bool):
        return None, "Invalid folder ID."

    text = str(raw_value).strip()

    if text == "" or text.lower() == "null":
        return None, None

    if not text.isdigit():
        return None, "Invalid folder ID."

    folder = db.session.get(Folder, int(text))

    if folder is None:
        return None, "Folder not found."

    return folder, None


def show_value(value):
    """Readable text for audit details."""

    if value is None or value == "":
        return "(none)"

    return str(value)


def serialize_log(log):
    return {
        "timestamp": (
            log.created_at.isoformat()
            if log.created_at else ""
        ),
        "user": log.username or "System",
        "username": log.username or "System",
        "action": log.action,
        "document_id": log.document_id or "",
        "detail": log.detail or "",
        "ip_address": log.ip_address or "",
    }


# --------------------------------------------------
# LIST DOCUMENTS + SEARCH AND FILTERING
# --------------------------------------------------

@document_bp.route("/api/documents", methods=["GET"])
@login_required
def list_documents():

    search = request.args.get("q", "").strip()
    folder_id = request.args.get("folder_id", "").strip()
    status = request.args.get("status", "").strip()
    department = request.args.get("department", "").strip()
    document_type = request.args.get("document_type", "").strip()

    query = Document.query

    if not can_see_all():
        query = query.filter(
            Document.created_by == current_username()
        )

    if search:
        search_term = f"%{search}%"

        query = query.filter(
            db.or_(
                Document.name.ilike(search_term),
                Document.description.ilike(search_term),
                Document.reference_number.ilike(search_term),
                Document.department.ilike(search_term),
            )
        )

    if folder_id:
        if not folder_id.isdigit():
            return jsonify({
                "error": "Invalid folder ID."
            }), 400

        query = query.filter(
            Document.folder_id == int(folder_id)
        )

    if status:
        query = query.filter(
            Document.status.ilike(status)
        )

    if department:
        query = query.filter(
            Document.department.ilike(department)
        )

    if document_type:
        query = query.filter(
            Document.document_type.ilike(document_type)
        )

    documents = query.order_by(
        Document.created_at.desc()
    ).all()

    results = []

    for doc in documents:

        latest_version = (
            get_latest_version(doc)
            if doc.versions else None
        )

        results.append({
            "id": doc.id,
            "name": doc.name,
            "document_type": doc.document_type or "",
            "department": doc.department or "General",
            "folder": doc.folder.name if doc.folder else "Unassigned",
            "folder_id": doc.folder_id,
            "reference_number": doc.reference_number or "",
            "description": doc.description or "",
            "status": doc.status or "Draft",
            "retention_date": (
                doc.retention_date.isoformat()
                if doc.retention_date else ""
            ),
            "created_by": doc.created_by or "System",
            "uploaded_by": doc.created_by or "System",
            "created_at": (
                doc.created_at.isoformat()
                if doc.created_at else ""
            ),
            "legal_hold": bool(doc.legal_hold),
            "version_count": len(doc.versions),
            "latest_version": (
                latest_version.version_number
                if latest_version else 0
            ),
            "can_edit": can_modify(doc),
        })

    return jsonify(results)


# --------------------------------------------------
# UPLOAD NEW DOCUMENT
# --------------------------------------------------

@document_bp.route("/api/documents/upload", methods=["POST"])
@login_required
def upload_document():

    file = request.files.get("file")

    if file is None or not file.filename:
        return jsonify({
            "error": "Please select a file."
        }), 400

    original_name = secure_filename(file.filename)

    if not original_name or not allowed_file(original_name):
        return jsonify({
            "error": "File type is not allowed."
        }), 400

    file_bytes = file.read()

    if not file_bytes:
        return jsonify({
            "error": "The selected file is empty."
        }), 400

    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({
            "error": "Maximum file size is 10 MB."
        }), 413

    extension = original_name.rsplit(".", 1)[1].lower()

    if not validate_file_content(extension, file_bytes):
        return jsonify({
            "error": "The file content does not match its extension."
        }), 400

    # Optional folder selection (checked before saving anything)
    target_folder, folder_error = resolve_folder(
        request.form.get("folder_id")
    )

    if folder_error:
        return jsonify({
            "error": folder_error
        }), 400

    document_id = str(uuid.uuid4())
    stored_name = f"{uuid.uuid4().hex}.{extension}"

    destination = upload_folder() / stored_name

    try:
        with open(destination, "wb") as output:
            output.write(file_bytes)

        username = current_username() or "System"

        document = Document(
            id=document_id,
            name=original_name,
            folder_id=target_folder.id if target_folder else None,
            document_type=extension.upper(),
            department=(
                request.form.get("department", "General").strip()
                or "General"
            ),
            reference_number=(
                request.form.get("reference_number", "").strip()
                or None
            ),
            description=request.form.get("description", "").strip(),
            status="Draft",
            created_by=username,
            created_at=utcnow(),
        )

        version = DocumentVersion(
            document_id=document_id,
            version_number=1,
            stored_name=stored_name,
            size=len(file_bytes),
            sha256=hashlib.sha256(file_bytes).hexdigest(),
            uploaded_by=username,
            uploaded_at=utcnow(),
        )

        db.session.add(document)
        db.session.add(version)

        log_action(
            "UPLOAD",
            document_id,
            f"Uploaded {original_name} as version 1",
        )

        db.session.commit()

        return jsonify({
            "message": "Document uploaded successfully.",
            "id": document_id,
            "name": original_name,
            "version": 1,
            "folder_id": document.folder_id,
            "folder": (
                target_folder.name if target_folder else "Unassigned"
            ),
        }), 201

    except Exception:
        db.session.rollback()

        if destination.exists():
            destination.unlink()

        current_app.logger.exception(
            "Document upload failed"
        )

        return jsonify({
            "error": "Upload failed. Please try again."
        }), 500


# --------------------------------------------------
# MOVE DOCUMENT TO FOLDER
# Uploader or Admin only.
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/folder",
    methods=["PATCH"],
)
@login_required
def move_document_to_folder(document_id):

    document = get_document_or_404(document_id)

    if not can_modify(document):
        return jsonify({
            "error": (
                "Only the uploader or an administrator "
                "can move this document."
            )
        }), 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or "folder_id" not in data:
        return jsonify({
            "error": "folder_id is required (use null for Unassigned)."
        }), 400

    target_folder, folder_error = resolve_folder(data.get("folder_id"))

    if folder_error:
        status_code = 404 if folder_error == "Folder not found." else 400

        return jsonify({
            "error": folder_error
        }), status_code

    old_name = document.folder.name if document.folder else "Unassigned"
    new_name = target_folder.name if target_folder else "Unassigned"

    if document.folder_id == (target_folder.id if target_folder else None):
        return jsonify({
            "message": "Document is already in that folder.",
            "document_id": document.id,
            "folder_id": document.folder_id,
            "folder": new_name,
        })

    try:
        document.folder_id = target_folder.id if target_folder else None

        log_action(
            "MOVE",
            document.id,
            f"Moved {document.name} from {old_name} to {new_name}",
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Document move failed"
        )

        return jsonify({
            "error": "Could not move the document. Please try again."
        }), 500

    return jsonify({
        "message": "Document moved successfully.",
        "document_id": document.id,
        "folder_id": document.folder_id,
        "folder": new_name,
    })


# --------------------------------------------------
# SET OR RELEASE LEGAL HOLD - ADMIN ONLY
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/legal-hold",
    methods=["PATCH"],
)
@login_required
def set_legal_hold(document_id):

    if not is_admin():
        return jsonify({
            "error": "Administrator access required."
        }), 403

    document = get_document_or_404(document_id)

    data = request.get_json(silent=True)

    if (
        not isinstance(data, dict)
        or not isinstance(data.get("legal_hold"), bool)
    ):
        return jsonify({
            "error": "legal_hold must be true or false."
        }), 400

    new_value = data["legal_hold"]

    if bool(document.legal_hold) == new_value:
        return jsonify({
            "message": (
                "Document is already under legal hold."
                if new_value
                else "Document is not under legal hold."
            ),
            "document_id": document.id,
            "legal_hold": bool(document.legal_hold),
        })

    try:
        document.legal_hold = new_value

        log_action(
            "LEGAL_HOLD",
            document.id,
            (
                f"Placed legal hold on {document.name}"
                if new_value
                else f"Released legal hold on {document.name}"
            ),
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Legal hold update failed"
        )

        return jsonify({
            "error": "Could not update legal hold. Please try again."
        }), 500

    return jsonify({
        "message": (
            "Legal hold placed successfully."
            if new_value
            else "Legal hold released successfully."
        ),
        "document_id": document.id,
        "legal_hold": bool(document.legal_hold),
    })


# --------------------------------------------------
# EDIT DOCUMENT DETAILS (METADATA)
# Uploader or Admin only.
# Editable: department, reference_number, description,
# status, retention_date (YYYY-MM-DD or empty to clear)
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/metadata",
    methods=["PATCH"],
)
@login_required
def update_document_metadata(document_id):

    document = get_document_or_404(document_id)

    if not can_modify(document):
        return jsonify({
            "error": (
                "Only the uploader or an administrator "
                "can edit this document."
            )
        }), 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "error": "No changes were provided."
        }), 400

    editable_fields = {
        "department",
        "reference_number",
        "description",
        "status",
        "retention_date",
    }

    unknown_fields = set(data) - editable_fields

    if unknown_fields:
        return jsonify({
            "error": (
                "These fields cannot be edited: "
                + ", ".join(sorted(unknown_fields))
            )
        }), 400

    new_values = {}

    if "department" in data:
        value = str(data.get("department") or "").strip() or "General"

        if len(value) > 100:
            return jsonify({
                "error": "Department cannot exceed 100 characters."
            }), 400

        new_values["department"] = value

    if "reference_number" in data:
        value = str(data.get("reference_number") or "").strip()

        if len(value) > 100:
            return jsonify({
                "error": "Reference number cannot exceed 100 characters."
            }), 400

        new_values["reference_number"] = value or None

    if "description" in data:
        value = str(data.get("description") or "").strip()

        if len(value) > 2000:
            return jsonify({
                "error": "Description cannot exceed 2000 characters."
            }), 400

        new_values["description"] = value

    if "status" in data:
        raw_status = str(data.get("status") or "").strip().lower()

        if raw_status not in EDITABLE_STATUSES:
            return jsonify({
                "error": (
                    "Status must be Draft, Active, "
                    "Archived or Pending."
                )
            }), 400

        new_values["status"] = EDITABLE_STATUSES[raw_status]

    if "retention_date" in data:
        raw_date = data.get("retention_date")

        if raw_date is None or str(raw_date).strip() == "":
            new_values["retention_date"] = None

        else:
            try:
                new_values["retention_date"] = date.fromisoformat(
                    str(raw_date).strip()
                )
            except ValueError:
                return jsonify({
                    "error": "Retention date must be YYYY-MM-DD."
                }), 400

    changes = []

    for field, new_value in new_values.items():
        old_value = getattr(document, field)

        if field == "description":
            old_value = old_value or ""

        if old_value != new_value:
            changes.append((field, old_value, new_value))

    if not changes:
        return jsonify({
            "message": "No changes were needed.",
            "document_id": document.id,
        })

    try:
        for field, old_value, new_value in changes:
            setattr(document, field, new_value)

        detail_parts = []

        for field, old_value, new_value in changes:
            if field == "description":
                detail_parts.append("description updated")
            else:
                detail_parts.append(
                    f"{field}: {show_value(old_value)} "
                    f"-> {show_value(new_value)}"
                )

        log_action(
            "METADATA_UPDATE",
            document.id,
            f"Edited {document.name} ("
            + "; ".join(detail_parts)
            + ")",
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Document metadata update failed"
        )

        return jsonify({
            "error": "Could not update the document. Please try again."
        }), 500

    return jsonify({
        "message": "Document details updated successfully.",
        "document_id": document.id,
        "department": document.department or "General",
        "reference_number": document.reference_number or "",
        "description": document.description or "",
        "status": document.status or "Draft",
        "retention_date": (
            document.retention_date.isoformat()
            if document.retention_date else ""
        ),
    })


# --------------------------------------------------
# DOCUMENT ACTIVITY HISTORY
# Uploader or Admin only.
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/activity",
    methods=["GET"],
)
@login_required
def get_document_activity(document_id):

    document = get_document_or_404(document_id)

    if not can_modify(document):
        return jsonify({
            "error": (
                "Only the uploader or an administrator "
                "can view this document's activity."
            )
        }), 403

    logs = (
        AuditLog.query
        .filter_by(document_id=str(document.id))
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )

    return jsonify([serialize_log(log) for log in logs])


# --------------------------------------------------
# UPLOAD NEW DOCUMENT VERSION
# Uploader or Admin only.
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/versions",
    methods=["POST"],
)
@login_required
def upload_document_version(document_id):

    document = get_document_or_404(document_id)

    if not can_modify(document):
        return jsonify({
            "error": (
                "Only the uploader or an administrator "
                "can add a new version."
            )
        }), 403

    file = request.files.get("file")

    if file is None or not file.filename:
        return jsonify({
            "error": "Please select a file."
        }), 400

    original_name = secure_filename(file.filename)

    if not original_name or not allowed_file(original_name):
        return jsonify({
            "error": "File type is not allowed."
        }), 400

    original_extension = document.name.rsplit(".", 1)[-1].lower()
    new_extension = original_name.rsplit(".", 1)[-1].lower()

    if original_extension != new_extension:
        return jsonify({
            "error": "New version must have the same file extension."
        }), 400

    file_bytes = file.read()

    if not file_bytes:
        return jsonify({
            "error": "The selected file is empty."
        }), 400

    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({
            "error": "Maximum file size is 10 MB."
        }), 413

    if not validate_file_content(new_extension, file_bytes):
        return jsonify({
            "error": "The file content does not match its extension."
        }), 400

    latest = (
        DocumentVersion.query
        .filter_by(document_id=document_id)
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )

    next_version = latest.version_number + 1 if latest else 1

    stored_name = f"{uuid.uuid4().hex}.{new_extension}"
    destination = upload_folder() / stored_name

    try:
        with open(destination, "wb") as output:
            output.write(file_bytes)

        username = current_username() or "System"

        version = DocumentVersion(
            document_id=document.id,
            version_number=next_version,
            stored_name=stored_name,
            size=len(file_bytes),
            sha256=hashlib.sha256(file_bytes).hexdigest(),
            uploaded_by=username,
            uploaded_at=utcnow(),
        )

        db.session.add(version)

        log_action(
            "VERSION_UPLOAD",
            document.id,
            f"Uploaded version {next_version} of {document.name}",
        )

        db.session.commit()

        return jsonify({
            "message": "New document version uploaded successfully.",
            "document_id": document.id,
            "version": next_version,
            "name": document.name,
        }), 201

    except Exception:
        db.session.rollback()

        if destination.exists():
            destination.unlink()

        current_app.logger.exception(
            "Document version upload failed"
        )

        return jsonify({
            "error": "Version upload failed. Please try again."
        }), 500


# --------------------------------------------------
# GET DOCUMENT VERSION HISTORY
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/versions",
    methods=["GET"],
)
@login_required
def get_document_versions(document_id):

    document = get_document_or_404(document_id)

    versions = (
        DocumentVersion.query
        .filter_by(document_id=document.id)
        .order_by(DocumentVersion.version_number.desc())
        .all()
    )

    return jsonify({
        "document_id": document.id,
        "document_name": document.name,
        "versions": [
            {
                "id": version.id,
                "version_number": version.version_number,
                "size": version.size,
                "sha256": version.sha256,
                "uploaded_by": version.uploaded_by or "System",
                "uploaded_at": (
                    version.uploaded_at.isoformat()
                    if version.uploaded_at else ""
                ),
                "download_url": (
                    f"/api/documents/{document.id}/versions/"
                    f"{version.version_number}/download"
                ),
            }
            for version in versions
        ],
    })


# --------------------------------------------------
# DOWNLOAD SPECIFIC DOCUMENT VERSION
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/versions/"
    "<int:version_number>/download",
    methods=["GET"],
)
@login_required
def download_document_version(document_id, version_number):

    document = get_document_or_404(document_id)

    version = (
        DocumentVersion.query
        .filter_by(
            document_id=document.id,
            version_number=version_number,
        )
        .first_or_404()
    )

    log_action(
        "VERSION_DOWNLOAD",
        document.id,
        f"Downloaded version {version_number} of {document.name}",
    )

    db.session.commit()

    return send_from_directory(
        upload_folder(),
        version.stored_name,
        as_attachment=True,
        download_name=document.name,
    )


# --------------------------------------------------
# PREVIEW DOCUMENT
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/preview",
    methods=["GET"],
)
@login_required
def preview_document(document_id):

    document = get_document_or_404(document_id)
    version = get_latest_version(document)

    log_action(
        "VIEW",
        document.id,
        f"Previewed {document.name}",
    )

    db.session.commit()

    response = send_from_directory(
        upload_folder(),
        version.stored_name,
        as_attachment=False,
        download_name=document.name,
    )

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'self'"
    )

    return response


# --------------------------------------------------
# DOWNLOAD LATEST DOCUMENT VERSION
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>/download",
    methods=["GET"],
)
@login_required
def download_document(document_id):

    document = get_document_or_404(document_id)
    version = get_latest_version(document)

    log_action(
        "DOWNLOAD",
        document.id,
        f"Downloaded {document.name}",
    )

    db.session.commit()

    return send_from_directory(
        upload_folder(),
        version.stored_name,
        as_attachment=True,
        download_name=document.name,
    )


# --------------------------------------------------
# DELETE DOCUMENT - ADMIN ONLY
# --------------------------------------------------

@document_bp.route(
    "/api/documents/<document_id>",
    methods=["DELETE"],
)
@login_required
def delete_document(document_id):

    if not is_admin():
        return jsonify({
            "error": "Administrator access required."
        }), 403

    document = get_document_or_404(document_id)

    if document.legal_hold:
        return jsonify({
            "error": (
                "This document is under legal hold "
                "and cannot be deleted."
            )
        }), 409

    if (
        document.retention_date
        and document.retention_date > utcnow().date()
    ):
        return jsonify({
            "error": (
                "This document must be retained until "
                f"{document.retention_date.isoformat()} "
                "and cannot be deleted yet."
            )
        }), 409

    filenames = [
        version.stored_name
        for version in document.versions
        if version.stored_name
    ]

    log_action(
        "DELETE",
        document.id,
        f"Deleted {document.name}",
    )

    db.session.delete(document)
    db.session.commit()

    for filename in filenames:
        try:
            (upload_folder() / filename).unlink(missing_ok=True)

        except OSError:
            current_app.logger.exception(
                "Could not remove stored file %s",
                filename,
            )

    return jsonify({
        "message": "Document deleted successfully."
    })


# --------------------------------------------------
# VIEW AUDIT LOGS - ADMIN ONLY
# --------------------------------------------------

@document_bp.route("/api/audit", methods=["GET"])
@login_required
def get_audit_logs():

    if not is_admin():
        return jsonify({
            "error": "Administrator access required."
        }), 403

    action = request.args.get("action", "").strip().upper()

    if action and action not in ALLOWED_ACTIONS:
        return jsonify({
            "error": "Invalid action filter."
        }), 400

    query = AuditLog.query

    if action:
        query = query.filter_by(action=action)

    logs = query.order_by(
        AuditLog.created_at.desc()
    ).limit(500).all()

    return jsonify([serialize_log(log) for log in logs])


# --------------------------------------------------
# LIST USERS - ADMIN ONLY
# --------------------------------------------------

@document_bp.route("/api/users", methods=["GET"])
@login_required
def get_users():

    if not is_admin():
        return jsonify({
            "error": "Administrator access required."
        }), 403

    users = User.query.order_by(User.id.asc()).all()

    return jsonify([
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
        for user in users
    ]), 200


# --------------------------------------------------
# CHANGE USER ROLE - ADMIN ONLY
# --------------------------------------------------

@document_bp.route(
    "/api/users/<int:user_id>/role",
    methods=["PATCH"],
)
@login_required
def update_user_role(user_id):

    if not is_admin():
        return jsonify({
            "error": "Administrator access required."
        }), 403

    if user_id == current_user.id:
        return jsonify({
            "error": "You cannot change your own role."
        }), 400

    data = request.get_json(silent=True) or {}
    new_role = data.get("role")

    if new_role not in {"Admin", "User"}:
        return jsonify({
            "error": "Role must be Admin or User."
        }), 400

    user = db.session.get(User, user_id)

    if user is None:
        return jsonify({
            "error": "User not found."
        }), 404

    if user.role == "Admin" and new_role != "Admin":

        admin_count = User.query.filter_by(role="Admin").count()

        if admin_count <= 1:
            return jsonify({
                "error": "Cannot remove the last Admin."
            }), 409

    old_role = user.role
    user.role = new_role

    log_action(
        "ROLE_CHANGE",
        detail=(
            f"Changed {user.username} role "
            f"from {old_role} to {new_role}"
        ),
    )

    db.session.commit()

    return jsonify({
        "message": "User role updated successfully.",
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    })