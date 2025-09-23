from flask import Blueprint, request, jsonify, current_app
from backend.models.form_links import FORM_LINK
from backend.models.forms import FORM
from backend.models.form_responses import FORM_RESPONSE
from backend.middleware.auth import jwt_required
from backend import socketio

form_response_bp = Blueprint("form_response", __name__)

@form_response_bp.route("/submit/<slug>", methods=["POST"])
def submit_response(slug):
    try:
        link = FORM_LINK.get_by_slug(slug)
        if not link:
            return jsonify({"error": "Form link not found or expired"}), 404
        
        form = FORM.get_by_id(link["form_id"])
        if not form:
            return jsonify({"error": "Form not found"}), 404
        
        data = request.get_json()
        current_app.logger.info(f"Received form submission data: {data}")
        
        # Handle both 'answers' and 'responses' keys for flexibility
        raw_answers = data.get("answers") or data.get("responses", {})
        if not raw_answers:
            return jsonify({"error": "Answers are required"}), 400
        
        # Transform the answers to match expected format
        structured_answers = []
        for idx, question in enumerate(form["questions"]):
            question_key = str(idx + 1)
            if question_key in raw_answers:
                structured_answers.append({
                    "question": question.get("question", question.get("text", f"Question {idx + 1}")),
                    "answer": raw_answers[question_key]
                })
        
        current_app.logger.info(f"Structured answers: {structured_answers}")
        
        responder_ip = request.remote_addr
        response_id = FORM_RESPONSE.submit(str(form["_id"]), structured_answers, responder_ip)
        
        # Emit real-time updates
        try:
            results = FORM_RESPONSE.get_poll_results(str(form["_id"]))
            socketio.emit("form_update", {"form_id": str(form["_id"]), "results": results}, room=str(form["_id"]))
        except Exception as e:
            current_app.logger.warning(f"Failed to emit socket update: {e}")
        
        return jsonify({
            "message": "Response submitted successfully", 
            "response_id": response_id
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Form submission error: {e}")
        return jsonify({"error": "Failed to submit form response"}), 500


@form_response_bp.route("/form/<form_id>", methods=["GET"])
@jwt_required
def list_response(form_id):
    current_app.logger.info(f"Getting responses for form_id: {form_id}")
    responses = FORM_RESPONSE.get_by_form_id(form_id)
    current_app.logger.info(f"Found {len(responses)} responses")
    
    for r in responses:
        r["_id"] = str(r["_id"])
        r["form_id"] = str(r["form_id"])
        
        # Log original answers structure
        current_app.logger.info(f"Original answers structure: {r.get('answers', 'NO ANSWERS')}")
        
        # Transform answers from array to object for frontend compatibility
        if "answers" in r and isinstance(r["answers"], list):
            answers_obj = {}
            for ans in r["answers"]:
                if "question" in ans and "answer" in ans:
                    answers_obj[ans["question"]] = ans["answer"]
            r["answers"] = answers_obj
            current_app.logger.info(f"Transformed answers: {r['answers']}")
    
    return jsonify(responses), 200

@form_response_bp.route("/results/<form_id>", methods=["GET"])
def poll_results(form_id):
    try:
        current_app.logger.info(f"Getting poll results for form_id: {form_id}")
        results = FORM_RESPONSE.get_poll_results(form_id)
        current_app.logger.info(f"Poll results: {results}")
        return jsonify(results), 200
    except Exception as e:
        current_app.logger.error(f"Error getting poll results for form_id {form_id}: {e}")
        return jsonify({"error": "Failed to get poll results"}), 500
