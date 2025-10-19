from flask import Blueprint, request, jsonify, current_app, g 
from backend.utils.exam_validation import validate_exam_payload, validate_question_payload
from backend.models.exam import exam_doc
from backend.models.question import question_doc
from datetime import datetime 
from bson import ObjectId
from backend.middleware.auth import token_required

exam_manage_bp = Blueprint("exam_manage", __name__, url_prefix="/api/exam/manage")

def require_exam_owner(exam):
    return str(exam.get("owner_id")) == str(g.current_user["_id"])

@exam_manage_bp.route("/create", methods=["POST"])
@token_required
def create_exam():
    """
    body: {title, description, start_time, endtime, duration, code, settings}
    """
    try:
        data = request.get_json() or ()
        ok, err = validate_exam_payload(data)
        if not ok:
            return jsonify({"error": err}), 400
        
        code = data.get("code").strip()
        db = current_app.mongo.db 
        if db.exams.find_one({"code": code}):
            return jsonify({"error": "Exam code already exists"}), 400
        
        exam = exam_doc(
            title=data.get("title"),
            description=data.get("description", ""),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            duration_seconds=int(data.get("duration_seconds", 3600)),
            owner_id=g.current_user["_id"],
            code=code,
            settings=data.get("settings")
        )
        res = db.exams.insert_one(exam)
        return jsonify({"message": "Exam created", "exam_id": str(res.inserted_id)}), 201
    except Exception as e:
        current_app.logger.exception("Create exam error")
        return jsonify({"error": "Failed to create exam", "details": str(e)}), 500
    
    
@exam_manage_bp.route("/<exam_id>/publish", methods=["POST"])
@token_required
def publish_exam(exam_id):
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403
        
        db.exams.update_one({"_id": exam["_id"]}, {"$set": {"status": "published", "updated_at": datetime.utcnow()}})
        return jsonify({"message": "Exam published"}), 200
    except Exception as e:
        current_app.logger.exception("Published exam error")
        return jsonify({"error": "Failed to publish exam"}), 500
    
@exam_manage_bp.route("/<exam_id>/questions", methods=["POST"])
@token_required
def add_question(exam_id):
    """
    Body depends on question type
    """
    try:
        data = request.get_json() or {}
        data["exam_id"] = exam_id
        ok, err = validate_question_payload(data)
        if not ok:
            return jsonify({"error": err}), 400
        
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403
        
        q = question_doc(
            exam_id=exam["_id"],
            qtype=data["type"],
            prompt=data["prompt"],
            options=data.get("options"),
            answer_key=data.get("answer_key"),
            points=int(data.get("points", 1)),
            media=data.get("media"),
            shuffle_options=data.get("shuffle_options", True)
        )
        res = db.exam_questions.insert_one(q)
        # increment 
        db.exams.update_one({"_id": exam["_id"]}, {"$inc": {"question_count": 1}, "$set": {"updated_at": datetime.utcnow()}})
        return jsonify({"message": "Question added", "question_id": str(res.inserted_one)}), 201
    except Exception as e:
        current_app.logger.exception("Add question error")
        return jsonify({"error": "Failed to add question", "details": str(e)}), 500