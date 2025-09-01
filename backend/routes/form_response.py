from flask import Blueprint, request, jsonify
from backend.models.form_links import FORM_LINK
from backend.models.forms import FORM
from backend.models.form_responses import FORM_RESPONSE
from backend.middleware.auth import jwt_required
from backend import socketio

form_response_bp = Blueprint("form_response", __name__)

@form_response_bp.route("/submit/<slug>", methods=["POST"])
def submit_response(slug):
    link = FORM_LINK.get_by_slug(slug)
    if not link:
        return jsonify({"error": "invalid or expired form link"}), 404
    
    form = FORM.get_by_id(link["form_id"])
    if not form:
        return jsonify({"error": "invalid or expired form link"}), 404
    
    data = request.get_json()
    answers = data.get("answers", [])
    if not answers:
        return jsonify({"error": "Answers are required"}), 400
    
    responder_ip = request.remote_addr
    response_id = FORM_RESPONSE.submit(str(form["_id"]), answers, responder_ip)
    
    results = FORM_RESPONSE.get_poll_results(str(form["_id"]))
    socketio.emit("form_update", {"form_id": str(form["_id"]), "results": results}, room=str(form["_id"]))
    
    return jsonify({"message": "Response submitted", "response_id": response_id})


@form_response_bp.route("/form/<form_id>", methods=["GET"])
@jwt_required
def list_response(form_id):
    responses = FORM_RESPONSE(form_id)
    for r in responses:
        r["_id"] = str(r["_id"])
        r["form_id"] = str(r["form_id"])
    return jsonify(responses), 200

@form_response_bp.route("/results/<form_id>", methods=["GET"])
def poll_results(form_id):
    results = FORM_RESPONSE.get_poll_results(form_id)
    return jsonify(results), 200