import os

from flask import Flask, jsonify, render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db, login_manager
from app.models.document import AuditLog, Document
from app.models.user import User


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("EDMS_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("Set EDMS_SECRET_KEY before starting EDMS.")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///../storage/edms.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "auth.login"


from app.routes.auth_routes import auth_bp
from app.routes.document_routes import document_bp
from app.routes.folder_routes import folder_bp
from app.routes.user_routes import user_bp

app.register_blueprint(auth_bp)
app.register_blueprint(document_bp)
app.register_blueprint(folder_bp)
app.register_blueprint(user_bp)


@app.context_processor
def inject_user_permissions():
    is_admin = (
        current_user.is_authenticated
        and getattr(current_user, "role", None) == "Admin"
    )

    return {"is_admin": is_admin}


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html")


@app.route("/api/dashboard/stats", methods=["GET"])
@login_required
def dashboard_stats():

    total_documents = Document.query.count()
    legal_hold_documents = Document.query.filter_by(legal_hold=True).count()

    status_rows = (
        db.session.query(Document.status, func.count(Document.id))
        .group_by(Document.status)
        .all()
    )
    department_rows = (
        db.session.query(Document.department, func.count(Document.id))
        .group_by(Document.department)
        .all()
    )

    status_stats = [{"name": status or "Unspecified", "count": count} for status, count in status_rows]
    department_stats = [{"name": department or "Unspecified", "count": count} for department, count in department_rows]

    response = {
        "documents": {
            "total": total_documents,
            "legal_hold": legal_hold_documents,
            "by_status": status_stats,
            "by_department": department_stats,
        },
        "users": None,
        "recent_activity": [],
        "approval_workflow_configured": False,
    }

    if current_user.role == "Admin":
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        response["users"] = {"total": total_users, "active": active_users}

        recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
        response["recent_activity"] = [
            {
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "user": log.user or "System",
                "action": log.action,
                "document_id": log.document_id,
                "detail": log.detail or "",
            }
            for log in recent_logs
        ]

    return jsonify(response)


__all__ = ["app", "db", "login_manager"]