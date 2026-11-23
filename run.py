import os
from datetime import timedelta

from flask import Flask, render_template, jsonify, request
from flask_login import (
    LoginManager,
    login_required,
    current_user
)
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.document import Document, AuditLog


# ==========================================
# APPLICATION CONFIGURATION
# ==========================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("EDMS_SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "Set EDMS_SECRET_KEY before starting EDMS."
    )

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///../storage/edms.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Upload size limit: 25 MB (change the first number to adjust)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


# ==========================================
# SESSION AND COOKIE SECURITY (Step 3)
# ==========================================

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set this to True only when the site runs on HTTPS
app.config["SESSION_COOKIE_SECURE"] = False

app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)


# ==========================================
# CSRF PROTECTION (Step 4)
# ==========================================

# CSRF is ENFORCED (turned on in step 4d).
app.config["WTF_CSRF_CHECK_DEFAULT"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = None

csrf = CSRFProtect()
csrf.init_app(app)


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

db.init_app(app)


# ==========================================
# FLASK LOGIN CONFIGURATION
# ==========================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None

    # A deactivated user is treated as logged out
    if user is None or not user.is_active:
        return None

    return user


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(413)
def too_large(error):
    return jsonify({
        "error": "File is too large. The maximum size is 25 MB."
    }), 413


# ==========================================
# SECURITY HEADERS + CSRF TOKEN FOR PAGES
# ==========================================

# This small script adds the CSRF token to:
#  1) every POST / PUT / PATCH / DELETE made with fetch()
#  2) every plain form submit (for example the Logout buttons)
CSRF_SCRIPT = """
<script>
(function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.content : "";
  var originalFetch = window.fetch;

  window.fetch = function (input, init) {
    init = init || {};
    var method = (init.method || (input && input.method) || "GET").toUpperCase();

    if (["POST", "PUT", "PATCH", "DELETE"].indexOf(method) !== -1) {
      var url = (typeof input === "string") ? input : ((input && input.url) || "");
      var isAbsolute = /^https?:\\/\\//i.test(url);
      var sameOrigin = !isAbsolute || url.indexOf(location.origin) === 0;

      if (sameOrigin) {
        var headers = new Headers(init.headers || (input && input.headers) || {});
        headers.set("X-CSRFToken", token);
        init.headers = headers;
      }
    }

    return originalFetch.call(this, input, init);
  };

  // Add the token to plain form submits (like Logout)
  var originalSubmit = HTMLFormElement.prototype.submit;

  function addToken(form) {
    var method = (form.method || "GET").toUpperCase();
    if (method === "GET") return;
    if (form.querySelector('input[name="csrf_token"]')) return;

    var field = document.createElement("input");
    field.type = "hidden";
    field.name = "csrf_token";
    field.value = token;
    form.appendChild(field);
  }

  HTMLFormElement.prototype.submit = function () {
    addToken(this);
    return originalSubmit.call(this);
  };

  document.addEventListener("submit", function (event) {
    addToken(event.target);
  }, true);
})();
</script>
"""


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Put the CSRF token and script into normal HTML pages
    # (the login page already has its own hidden token field).
    if (
        response.mimetype == "text/html"
        and not response.direct_passthrough
        and request.endpoint not in ("auth.login", "static")
    ):
        body = response.get_data(as_text=True)

        if "</head>" in body and 'name="csrf-token"' not in body:
            token = generate_csrf()
            snippet = (
                '<meta name="csrf-token" content="' + token + '">'
                + CSRF_SCRIPT
            )
            body = body.replace("</head>", snippet + "</head>", 1)
            response.set_data(body)

    return response


# ==========================================
# BLUEPRINT REGISTRATION
# ==========================================

from app.routes.auth_routes import auth_bp
from app.routes.document_routes import (
    document_bp,
    can_see_all,
    current_username
)
from app.routes.user_routes import user_bp
from app.routes.folder_routes import folder_bp
from app.routes.approval_routes import approval_bp

app.register_blueprint(auth_bp)
app.register_blueprint(document_bp)
app.register_blueprint(user_bp)
app.register_blueprint(folder_bp)
app.register_blueprint(approval_bp)


# ==========================================
# GLOBAL USER PERMISSIONS
# ==========================================

@app.context_processor
def inject_user_permissions():

    is_admin = (
        current_user.is_authenticated
        and getattr(current_user, "role", None) == "Admin"
    )

    return {
        "is_admin": is_admin
    }


# ==========================================
# MAIN DASHBOARD
# ==========================================

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html")


# ==========================================
# DASHBOARD STATISTICS API
# ==========================================

def limit_to_visible(query):
    # Same rule as the document list: normal users only
    # count documents they uploaded (in strict mode).
    if not can_see_all():
        query = query.filter(
            Document.created_by == current_username()
        )
    return query


@app.route("/api/dashboard/stats", methods=["GET"])
@login_required
def dashboard_stats():

    total_documents = limit_to_visible(
        Document.query
    ).count()

    legal_hold_documents = limit_to_visible(
        Document.query
    ).filter_by(
        legal_hold=True
    ).count()

    status_rows = (
        limit_to_visible(
            db.session.query(
                Document.status,
                func.count(Document.id)
            )
        )
        .group_by(Document.status)
        .all()
    )

    department_rows = (
        limit_to_visible(
            db.session.query(
                Document.department,
                func.count(Document.id)
            )
        )
        .group_by(Document.department)
        .all()
    )

    status_stats = [
        {
            "name": status or "Unspecified",
            "count": count
        }
        for status, count in status_rows
    ]

    department_stats = [
        {
            "name": department or "Unspecified",
            "count": count
        }
        for department, count in department_rows
    ]

    response = {
        "documents": {
            "total": total_documents,
            "legal_hold": legal_hold_documents,
            "by_status": status_stats,
            "by_department": department_stats
        },
        "users": None,
        "recent_activity": [],
        "approval_workflow_configured": False
    }

    if current_user.role == "Admin":

        total_users = User.query.count()

        active_users = User.query.filter_by(
            is_active=True
        ).count()

        response["users"] = {
            "total": total_users,
            "active": active_users
        }

        recent_logs = (
            AuditLog.query
            .order_by(AuditLog.created_at.desc())
            .limit(8)
            .all()
        )

        response["recent_activity"] = [
            {
                "timestamp": (
                    log.created_at.isoformat()
                    if log.created_at else None
                ),
                "user": log.username or "System",
                "action": log.action,
                "document_id": log.document_id,
                "detail": log.detail or ""
            }
            for log in recent_logs
        ]

    return jsonify(response)


# ==========================================
# APPLICATION START
# ==========================================

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )