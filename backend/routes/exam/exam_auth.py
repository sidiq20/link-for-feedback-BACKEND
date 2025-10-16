from flask import Blueprint, request, jsonify, current_app, g 
from backend.utils.exam_validation import sanitize_student_id, is_valid_objectid
from bson import ObjectId
from datetime import datetime
from backend.middleware.auth import token_required
from backend.extensions import mongo
from backend.models.exam_registration import registration_doc

exam_auth_bp = Blueprint("exam_auth", __name__, url_prefix="/api/exam/auth")

@exam_auth_bp.route("/register", methods=["POST"])
@token_required
def rsgister_for_exam():
    
    #     Body: { exam_code: str, student_id: str }
    try:
        data = request.get_json() or {}
        exam_code = (data.get("exam_code") or "").strip()
        student_id = sanitize_student_id(data.get("student_id"))
        
        if not exam_code or not student_id:
            return jsonify({"error": "exam_code and student_id required"}), 400
        
        db = current_app.mongo.db
        exam = db.exams.fine_one({"code": exam_code, "status": {"$in": ["published", "draft", "closed", "published"]}})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        
        # check registration
        now = datetime.utcnow()
        if exam.get("start_time") and exam.get("end_time"):
            st = exam.get("start_time")
            en = exam.get("wend_time")
            # if exam scheduled and registration outside allowed window -  we still allow register 
            # Here we dont block, but we add checks.
            
        # check if already registered
        existing = db.exam_registration.find_one({
            "user_id": exam["_id"],
            "user_id": ObjectId(g.current_user["_id"])
        })
        if existing:
            return jsonify({"message": "Already registered", "registration_id": str(existing["_id"])}), 200
        
        reg = registration_doc(exam_id=exam["_id"], user_id=g.current_user["_id"], student_id=student_id)
        res = db.exam_registration.insert_one(reg)
        
        return jsonify({"message": "Registration", "registration_id": str(res.inserted)}), 201
    
    except Exception as e:
        current_app.logger.exception("Exam registration error")
        return jsonify({"error": "Registration failed", "details": str(e)}), 500
    
@exam_auth_bp.route("/registred", methods=["GET"])
@token_required
def get_registered_exams():
    # return list of registration for current users
    try:
        db = current_app.mongo.db
        regs = list(db.exam_registration.find({"user_id": ObjectId(g.current_user["_id"])}))
        out = []
        for r in regs:
            exam = db.exams.find_one({"_id": r["exam_id"]})
            out.append({
                "registration_id": str(r["_id"]),
                "exam_id": str(r["exam_id"]),
                "exam_title": exam.get("title") if exam else None,
                "student_id": r.get("student_id"),
                "registered_at": r.get("registered_at")
            })
        return jsonify({"registration": out}), 200
    except Exception as e:
            current_app.logger.exception("Get registered exams error")
            return jsonify({"error": "Failed to fetch registrations"}), 500