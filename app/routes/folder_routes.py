from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.document import Folder


folder_bp = Blueprint("folders", __name__)


# ==========================================
# HELPERS
# ==========================================

def would_create_loop(folder, new_parent):
    """
    Return True if making new_parent the parent of folder would
    create a loop (folder is new_parent or one of its ancestors).
    """

    current = new_parent
    seen = set()

    while current is not None:
        if current.id == folder.id:
            return True

        if current.id in seen:
            return True

        seen.add(current.id)
        current = current.parent

    return False


# ==========================================
# FOLDER MANAGEMENT PAGE
# ==========================================

@folder_bp.route("/folders", methods=["GET"])
@login_required
def folders_page():
    return render_template("folders.html")


# ==========================================
# GET ALL FOLDERS
# ==========================================

@folder_bp.route("/api/folders", methods=["GET"])
@login_required
def get_folders():

    try:
        folders = Folder.query.order_by(Folder.name.asc()).all()

        result = []

        for folder in folders:
            result.append({
                "id": folder.id,
                "name": folder.name,
                "parent_id": folder.parent_id,
                "document_count": len(folder.documents),
                "subfolder_count": len(folder.subfolders),
                "created_at": (
                    folder.created_at.isoformat()
                    if folder.created_at else None
                )
            })

        return jsonify(result), 200

    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Unable to retrieve folders."
        }), 500


# ==========================================
# CREATE FOLDER
# ==========================================

@folder_bp.route("/api/folders", methods=["POST"])
@login_required
def create_folder():

    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    parent_id = data.get("parent_id")

    if not name:
        return jsonify({
            "error": "Folder name is required."
        }), 400

    if len(name) > 120:
        return jsonify({
            "error": "Folder name cannot exceed 120 characters."
        }), 400

    if parent_id is not None:
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Invalid parent folder ID."
            }), 400

        if not db.session.get(Folder, parent_id):
            return jsonify({
                "error": "Parent folder not found."
            }), 404

    try:
        folder = Folder(
            name=name,
            parent_id=parent_id
        )

        db.session.add(folder)
        db.session.commit()

        return jsonify({
            "message": "Folder created successfully.",
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "parent_id": folder.parent_id
            }
        }), 201

    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Unable to create folder."
        }), 500


# ==========================================
# RENAME / MOVE FOLDER
# Accepts "name", "parent_id", or both.
# parent_id = null moves the folder to the top level.
# ==========================================

@folder_bp.route(
    "/api/folders/<int:folder_id>",
    methods=["PATCH"]
)
@login_required
def update_folder(folder_id):

    folder = db.session.get(Folder, folder_id)

    if not folder:
        return jsonify({
            "error": "Folder not found."
        }), 404

    data = request.get_json(silent=True) or {}

    has_name = "name" in data
    has_parent = "parent_id" in data

    if not has_name and not has_parent:
        return jsonify({
            "error": "Provide a new name or a parent_id."
        }), 400

    new_name = folder.name

    if has_name:
        new_name = (data.get("name") or "").strip()

        if not new_name:
            return jsonify({
                "error": "New folder name is required."
            }), 400

        if len(new_name) > 120:
            return jsonify({
                "error": "Folder name cannot exceed 120 characters."
            }), 400

    new_parent_id = folder.parent_id

    if has_parent:
        raw_parent = data.get("parent_id")

        if raw_parent is None:
            new_parent_id = None

        else:
            try:
                parent_id = int(raw_parent)
            except (TypeError, ValueError):
                return jsonify({
                    "error": "Invalid parent folder ID."
                }), 400

            parent = db.session.get(Folder, parent_id)

            if not parent:
                return jsonify({
                    "error": "Parent folder not found."
                }), 404

            if parent.id == folder.id:
                return jsonify({
                    "error": "A folder cannot be its own parent."
                }), 400

            if would_create_loop(folder, parent):
                return jsonify({
                    "error": (
                        "A folder cannot be moved into "
                        "one of its own subfolders."
                    )
                }), 400

            new_parent_id = parent.id

    name_changed = has_name and new_name != folder.name
    parent_changed = has_parent and new_parent_id != folder.parent_id

    if not name_changed and not parent_changed:
        return jsonify({
            "message": "No changes were needed.",
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "parent_id": folder.parent_id
            }
        }), 200

    try:
        if name_changed:
            folder.name = new_name

        if parent_changed:
            folder.parent_id = new_parent_id

        db.session.commit()

        if name_changed and parent_changed:
            message = "Folder updated successfully."
        elif parent_changed:
            message = "Folder moved successfully."
        else:
            message = "Folder renamed successfully."

        return jsonify({
            "message": message,
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "parent_id": folder.parent_id
            }
        }), 200

    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Unable to update folder."
        }), 500


# ==========================================
# DELETE EMPTY FOLDER
# ==========================================

@folder_bp.route(
    "/api/folders/<int:folder_id>",
    methods=["DELETE"]
)
@login_required
def delete_folder(folder_id):

    folder = db.session.get(Folder, folder_id)

    if not folder:
        return jsonify({
            "error": "Folder not found."
        }), 404

    if folder.documents:
        return jsonify({
            "error": "Cannot delete a folder containing documents."
        }), 400

    if folder.subfolders:
        return jsonify({
            "error": "Cannot delete a folder containing subfolders."
        }), 400

    try:
        db.session.delete(folder)
        db.session.commit()

        return jsonify({
            "message": "Folder deleted successfully."
        }), 200

    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Unable to delete folder."
        }), 500