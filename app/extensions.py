from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


@login_manager.unauthorized_handler
def unauthorized():
    from flask import jsonify, redirect, request, url_for

    if request.path.startswith("/api/"):
        return jsonify({"error": "Please log in first"}), 401

    return redirect(url_for("auth.login"))


@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User

    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None