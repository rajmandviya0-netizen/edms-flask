
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User

user_bp = Blueprint("users", __name__)


def admin_required():
    return (
        current_user.is_authenticated
        and getattr(current_user, "role", None) == "Admin"
    )


def error(message, status):
    return jsonify({"error": message}), status


def get_user_data(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": (
            user.created_at.isoformat()
            if user.created_at else None
        )
    }


# USER MANAGEMENT PAGE
@user_bp.route("/admin/users")
@login_required
def user_management():

    if not admin_required():
        return error("Administrator access required.", 403)

    return render_template("user_management.html")


# CREATE USER
@user_bp.route("/api/users", methods=["POST"])
@login_required
def create_user():

    if not admin_required():
        return error("Administrator access required.", 403)

    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    role = data.get("role", "User")

    if not username or not email or not password:
        return error("All fields are required.", 400)

    if len(username) > 80 or len(email) > 255:
        return error("Username or email is too long.", 400)

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return error("Enter a valid email address.", 400)

    if role not in {"Admin", "User"}:
        return error("Invalid role.", 400)

    if not isinstance(password, str) or len(password) < 12:
        return error("Password must contain at least 12 characters.", 400)

    user = User(
        username=username,
        email=email,
        role=role,
        is_active=True
    )

    try:
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        return error("Username or email already exists.", 409)

    except ValueError as exc:
        db.session.rollback()
        return error(str(exc), 400)

    return jsonify({
        "message": "User created successfully.",
        "user": get_user_data(user)
    }), 201


# EDIT USER
@user_bp.route("/api/users/<int:user_id>", methods=["PATCH"])
@login_required
def edit_user(user_id):

    if not admin_required():
        return error("Administrator access required.", 403)

    user = db.session.get(User, user_id)

    if user is None:
        return error("User not found.", 404)

    data = request.get_json(silent=True) or {}

    username = data.get("username")
    email = data.get("email")

    if username is not None:
        username = str(username).strip()

        if not username or len(username) > 80:
            return error("Invalid username.", 400)

        user.username = username

    if email is not None:
        email = str(email).strip().lower()

        if (
            not email
            or len(email) > 255
            or "@" not in email
            or "." not in email.rsplit("@", 1)[-1]
        ):
            return error("Invalid email address.", 400)

        user.email = email

    try:
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        return error("Username or email already exists.", 409)

    return jsonify({
        "message": "User updated successfully.",
        "user": get_user_data(user)
    })


# ACTIVATE / DEACTIVATE USER
@user_bp.route("/api/users/<int:user_id>/status", methods=["PATCH"])
@login_required
def change_status(user_id):

    if not admin_required():
        return error("Administrator access required.", 403)

    if user_id == current_user.id:
        return error("You cannot deactivate your own account.", 400)

    user = db.session.get(User, user_id)

    if user is None:
        return error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    active = data.get("is_active")

    if not isinstance(active, bool):
        return error("is_active must be true or false.", 400)

    if user.role == "Admin" and not active:
        count = User.query.filter_by(
            role="Admin",
            is_active=True
        ).count()

        if count <= 1:
            return error("Cannot deactivate the last active Admin.", 409)

    user.is_active = active
    db.session.commit()

    return jsonify({
        "message": "Account status updated successfully.",
        "is_active": user.is_active
    })


# RESET PASSWORD
@user_bp.route("/api/users/<int:user_id>/password", methods=["PATCH"])
@login_required
def reset_password(user_id):

    if not admin_required():
        return error("Administrator access required.", 403)

    user = db.session.get(User, user_id)

    if user is None:
        return error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    password = data.get("password")

    if not isinstance(password, str) or len(password) < 12:
        return error(
            "Password must contain at least 12 characters.",
            400
        )

    try:
        user.set_password(password)
        db.session.commit()

    except ValueError as exc:
        db.session.rollback()
        return error(str(exc), 400)

    return jsonify({
        "message": "Password reset successfully."
    })
