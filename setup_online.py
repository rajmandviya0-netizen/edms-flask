import os
from run import app
from app import db

os.makedirs("instance", exist_ok=True)
os.makedirs("storage/uploads", exist_ok=True)
with app.app_context():
    db.create_all()
print("Database ready")