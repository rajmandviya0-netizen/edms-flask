from getpass import getpass
from run import app
from app import db
from app.models.user import User

with app.app_context():
    username = input("New admin username: ").strip()
    email = input("New admin email: ").strip()
    password = getpass("New admin password (12+ characters): ")

    if not username or not email or len(password) < 12:
        print("Please enter a username, email, and password of at least 12 characters.")
    elif User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        print("That username or email already exists. Choose different details.")
    else:
        user = User(username=username, email=email, role="Admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print("New Admin account created successfully.")
