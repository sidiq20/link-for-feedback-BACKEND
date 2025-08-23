from flask import Blueprint, request, jsonify, g 
from bson import ObjectId
from backend.middleware.auth import jwt_required
from backend.models.forms import FORM 

forms_bp = Blueprint("forms", __name__)

@forms_bp.route("/", methods=["POST"])
@jwt_required
def create_form():
    data = request.get_json()
    title = data.get("title")
    description = data.get("description", "") 
    questions = data.get("questions", [])
    
    if not title or not questions:
        return jsonify({"error": "Title and questions are required"}), 400 
    
    form_id = FORM.create(g.current_user["_id"])
    return jsonify({"message": "Form created", "form_id": form_id}), 201

@forms_bp.route("/", methods=["GET"])
@jwt_required
def list_forms():
    forms = FORM.get_by_user(g.current_user["_id"])
    for f in forms:
        f["_id"] = str(f["_id"])
    return jsonify(forms), 200

@forms_bp.route("/<form_id>", methods=["GET"])
@jwt_required
def get_form(form_id):
    form = FORM.get_by_id(form_id)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    form["_id"] = str(form["_id"])
    return jsonify(form), 200

@forms_bp.route("/<form_id>", methods=["PUT"])
@jwt_required
def update_form(form_id):
    data = request.get_json()
    FORM.update(form_id, data)
    return jsonify({"message": "Form updated"}), 200

@forms_bp.route("/<form_id>", methods=["DELETE"])
@jwt_required
def delete_form(form_id):
    FORM.delete(form_id)
    return jsonify({"message": "Form deleted"}), 200