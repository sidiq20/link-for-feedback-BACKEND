from flask import Blueprint, request, jsonify, g, make_response
from bson import ObjectId
from backend.middleware.auth import jwt_required
from backend.models.forms import FORM 
from flask_socketio import emit
from backend.models.response import RESPONSE
from backend import socketio
import uuid

forms_bp = Blueprint("forms", __name__)

def get_or_create_session(request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id

@forms_bp.route("<form_id>/vote", methods=["POST"])
def vote(form_id):
    data = request.json
    question_index = data.get("question_index")
    option_label = data.get("option")
    user_id = data.get("user_id")

    session_id = request.cookies.get("session_id")
    if not session_id:
        return jsonify({"error": "No session_id cookie. Load form first."}), 400

    form = FORM.get_by_id(form_id)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    
    try:
        question = form["questions"][question_index]
    except IndexError:
        return jsonify({"error": "Invalid question index"}), 400

    if RESPONSE.has_voted(form_id, question_index, user_id, session_id):
        return jsonify({"error": "You have already answered this question"}), 400

    if question["type"] == "poll":
        success, msg = FORM.vote(form_id, question_index, option_label)
        if not success:
            return jsonify({"error": msg}), 400
    elif question["type"] == "radio":
        RESPONSE.create(form_id, question_index, user_id, session_id, option_label)
    else:
        return jsonify({"error": f"Unsupported question type '{question['type']}'"}), 400

    if question["type"] == "poll":
        form = FORM.get_by_id(form_id)
        socketio.emit("vote_update", {
            "form_id": form_id,
            "questions": form["questions"]
        })

    return jsonify({"message": "Response recorded"}), 200



@forms_bp.route("/", methods=["POST"])
@jwt_required
def create_form():
    data = request.get_json()
    title = data.get("title")
    description = data.get("description", "") 
    questions = data.get("questions", [])
    
    if not title or not questions:
        return jsonify({"error": "Title and questions are required"}), 400 
    
    try:
        form_id = FORM.create(
            g.current_user["_id"],
            title,
            description,
            questions
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    return jsonify({
        "message": "Form created",
        "form_id": form_id
    }), 201

@forms_bp.route("/", methods=["GET"])
@jwt_required
def list_forms():
    forms = FORM.get_by_user(g.current_user["_id"])
    for f in forms:
        f["_id"] = str(f["_id"])
        
    print("DEBUG list_forms user_id:", g.current_user["_id"], type(g.current_user["_id"]))

    return jsonify(forms), 200

@forms_bp.route("/<form_id>", methods=["GET"])
@jwt_required
def get_form(form_id):
    form = FORM.get_by_id(form_id)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    form["_id"] = str(form["_id"])
    
    session_id = get_or_create_session(request)
    
    resp = jsonify(form)
    if "session_id" not in request.cookies:
        resp.set_cookie("session_id", session_id, httponly=True, samesite="Lax")
    return resp, 200

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

@forms_bp.route("<form_id>/results", methods=["GET"])
def get_results(form_id):
    results, error = FORM.get_results(form_id)
    if error:
        return jsonify({"error": error}), 404 
    return jsonify(results)