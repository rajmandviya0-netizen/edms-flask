from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user
)

from app.extensions import db
from app.models.user import User
from app.models.document import AuditLog

auth_bp = Blueprint("auth", __name__)

# Lockout settings
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 10


def utc_now_naive():
    # AuditLog times are saved as UTC without timezone info in SQLite
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_safe_next(target):
    # Only allow redirects to a path on this same site
    if not target:
        return False

    if not target.startswith("/") or target.startswith("//"):
        return False

    if "\\" in target:
        return False

    parsed = urlparse(target)
    return not parsed.netloc and not parsed.scheme


def log_auth_action(action, username, detail=None):
    # Adds an audit entry to the session. The caller commits.
    entry = AuditLog(
        username=(username or "")[:80] or None,
        action=action,
        document_id=None,
        detail=detail,
        ip_address=(request.remote_addr or "")[:45]
    )
    db.session.add(entry)


def is_locked_out(username):
    # Count failed logins in the last 10 minutes,
    # but only those after the user's last successful login.
    cutoff = utc_now_naive() - timedelta(minutes=LOCKOUT_MINUTES)

    last_login = (
        db.session.query(AuditLog.created_at)
        .filter(
            AuditLog.username == username,
            AuditLog.action == "LOGIN"
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )

    if last_login and last_login[0] and last_login[0] > cutoff:
        cutoff = last_login[0]

    failed_count = AuditLog.query.filter(
        AuditLog.username == username,
        AuditLog.action == "LOGIN_FAILED",
        AuditLog.created_at > cutoff
    ).count()

    return failed_count >= MAX_FAILED_ATTEMPTS


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()[:80]
        password = request.form.get("password", "")

        # 1) Locked out? Block before checking the password.
        if username and is_locked_out(username):
            flash(
                "Too many failed attempts. "
                "Try again in about 10 minutes.",
                "danger"
            )
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):

            if not user.is_active:
                log_auth_action(
                    "LOGIN_FAILED",
                    username,
                    "Inactive account"
                )
                db.session.commit()

                flash("Your account is inactive.", "danger")
                return redirect(url_for("auth.login"))

            log_auth_action("LOGIN", user.username, "Successful login")
            db.session.commit()

            login_user(user, remember=False, fresh=True)

            next_page = request.args.get("next")

            if is_safe_next(next_page):
                return redirect(next_page)

            return redirect(url_for("index"))

        # Wrong username or password
        log_auth_action(
            "LOGIN_FAILED",
            username or "(empty)",
            "Invalid username or password"
        )
        db.session.commit()

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():

    log_auth_action("LOGOUT", current_user.username, "User logged out")
    db.session.commit()

    logout_user()

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(url_for("auth.login"))