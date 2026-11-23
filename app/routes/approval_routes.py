from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.document import Document, AuditLog
from app.routes.document_routes import can_access, can_modify, is_admin

approval_bp = Blueprint("approval", __name__)


def error(message, status):
    return jsonify({"error": message}), status


def get_visible_document(document_id):
    doc = db.session.get(Document, document_id)

    if doc is None or not can_access(doc):
        return None

    return doc


def status_of(doc):
    return (doc.status or "").strip().lower()


def log_approval(action, doc, detail):
    db.session.add(AuditLog(
        username=current_user.username,
        action=action,
        document_id=doc.id,
        detail=detail,
        ip_address=(request.remote_addr or "")[:45]
    ))


# SUBMIT FOR APPROVAL (uploader or admin): Draft -> Pending
@approval_bp.route(
    "/api/documents/<document_id>/submit",
    methods=["POST"]
)
@login_required
def submit_for_approval(document_id):

    doc = get_visible_document(document_id)

    if doc is None:
        return error("Document not found.", 404)

    if not can_modify(doc):
        return error(
            "Only the uploader or an admin can submit this document.",
            403
        )

    if status_of(doc) != "draft":
        return error(
            "Only Draft documents can be submitted for approval.",
            409
        )

    doc.status = "Pending"

    log_approval(
        "APPROVAL_SUBMIT",
        doc,
        "Submitted " + doc.name + " for approval"
    )

    db.session.commit()

    return jsonify({
        "message": "Submitted for approval.",
        "status": doc.status
    })


# APPROVE (admin only): Pending -> Active
@approval_bp.route(
    "/api/documents/<document_id>/approve",
    methods=["POST"]
)
@login_required
def approve_document(document_id):

    if not is_admin():
        return error("Administrator access required.", 403)

    doc = get_visible_document(document_id)

    if doc is None:
        return error("Document not found.", 404)

    if status_of(doc) != "pending":
        return error(
            "Only Pending documents can be approved.",
            409
        )

    doc.status = "Active"

    log_approval(
        "APPROVAL_APPROVE",
        doc,
        "Approved " + doc.name
    )

    db.session.commit()

    return jsonify({
        "message": "Document approved.",
        "status": doc.status
    })


# REJECT (admin only): Pending -> Draft, with optional reason
@approval_bp.route(
    "/api/documents/<document_id>/reject",
    methods=["POST"]
)
@login_required
def reject_document(document_id):

    if not is_admin():
        return error("Administrator access required.", 403)

    doc = get_visible_document(document_id)

    if doc is None:
        return error("Document not found.", 404)

    if status_of(doc) != "pending":
        return error(
            "Only Pending documents can be rejected.",
            409
        )

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()[:200]

    doc.status = "Draft"

    detail = "Rejected " + doc.name

    if reason:
        detail = detail + ": " + reason

    log_approval("APPROVAL_REJECT", doc, detail)

    db.session.commit()

    return jsonify({
        "message": "Document rejected and returned to Draft.",
        "status": doc.status
    })