from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from backend.extensions import limiter
from datetime import datetime
from bson import ObjectId

exam_registration_bp = Blueprint("exam_registration", __name__, url_prefix="/api/exam/register")


@exam_registration_bp.route("", methods=["POST"])
@token_required
@limiter.limit('10 per minute')
def register_for_exam():
    """
    Register a student for an exam using exam code.
    Body: { "exam_code": "string" }
    """
    try:
        data = request.get_json() or {}
        exam_code = data.get("exam_code", "").strip()
        
        if not exam_code:
            return jsonify({"error": "Exam code is required"}), 400
        
        db = current_app.mongo.db
        
        # Find exam by code
        exam = db.exams.find_one({"code": exam_code, "status": "published"})
        if not exam:
            return jsonify({"error": "Exam not found or not available"}), 404
        
        # Check if already registered
        existing = db.exam_registration.find_one({
            "exam_id": exam["_id"],
            "user_id": g.current_user["_id"]
        })
        
        if existing:
            return jsonify({"error": "Already registered for this exam"}), 400
        
        # Create registration
        registration = {
            "_id": ObjectId(),
            "exam_id": exam["_id"],
            "user_id": g.current_user["_id"],
            "student_id": str(g.current_user["_id"]),
            "registered_at": datetime.utcnow(),
            "status": "registered"
        }
        
        db.exam_registration.insert_one(registration)
        
        # Increment registered count on exam
        db.exams.update_one(
            {"_id": exam["_id"]},
            {"$inc": {"registered_count": 1}}
        )
        
        return jsonify({
            "message": "Successfully registered for exam",
            "registration_id": str(registration["_id"]),
            "exam": {
                "_id": str(exam["_id"]),
                "title": exam["title"],
                "code": exam["code"],
                "start_time": exam.get("start_time"),
                "duration_seconds": exam.get("duration_seconds", 3600)
            }
        }), 201
        
    except Exception as e:
        current_app.logger.exception("Register for exam error")
        return jsonify({"error": "Failed to register", "details": str(e)}), 500


@exam_registration_bp.route("/list", methods=["GET"])
@token_required
def list_registrations():
    """
    Get all exams the current user is registered for.
    """
    try:
        db = current_app.mongo.db
        
        # Find all registrations for user
        registrations = list(db.exam_registration.find({
            "user_id": g.current_user["_id"]
        }))
        
        result = []
        for reg in registrations:
            exam = db.exams.find_one({"_id": reg["exam_id"]})
            if exam:
                result.append({
                    "registration_id": str(reg["_id"]),
                    "registered_at": reg.get("registered_at").isoformat() if reg.get("registered_at") else None,
                    "status": reg.get("status", "registered"),
                    "exam": {
                        "_id": str(exam["_id"]),
                        "title": exam["title"],
                        "description": exam.get("description", ""),
                        "code": exam["code"],
                        "start_time": exam.get("start_time"),
                        "end_time": exam.get("end_time"),
                        "duration_seconds": exam.get("duration_seconds", 3600),
                        "status": exam.get("status"),
                        "question_count": exam.get("question_count", 0)
                    }
                })
        
        return jsonify({"registrations": result}), 200
        
    except Exception as e:
        current_app.logger.exception("List registrations error")
        return jsonify({"error": "Failed to list registrations"}), 500


@exam_registration_bp.route("/<registration_id>", methods=["DELETE"])
@token_required
@limiter.limit('10 per minute')
def unregister_from_exam(registration_id):
    """
    Unregister from an exam.
    """
    try:
        db = current_app.mongo.db
        
        # Find registration
        registration = db.exam_registration.find_one({
            "_id": ObjectId(registration_id),
            "user_id": g.current_user["_id"]
        })
        
        if not registration:
            return jsonify({"error": "Registration not found"}), 404
        
        # Check if exam has already been taken
        session = db.exam_sessions.find_one({
            "exam_id": registration["exam_id"],
            "user_id": g.current_user["_id"]
        })
        
        if session:
            return jsonify({"error": "Cannot unregister after starting exam"}), 400
        
        # Delete registration
        db.exam_registration.delete_one({"_id": registration["_id"]})
        
        # Decrement registered count
        db.exams.update_one(
            {"_id": registration["exam_id"]},
            {"$inc": {"registered_count": -1}}
        )
        
        return jsonify({"message": "Successfully unregistered"}), 200
        
    except Exception as e:
        current_app.logger.exception("Unregister from exam error")
        return jsonify({"error": "Failed to unregister"}), 500


@exam_registration_bp.route("/check/<exam_code>", methods=["GET"])
@token_required
def check_exam_by_code(exam_code):
    """
    Check if an exam with given code exists and get its details.
    Used for preview before registration.
    """
    try:
        db = current_app.mongo.db
        
        exam = db.exams.find_one({"code": exam_code, "status": "published"})
        if not exam:
            return jsonify({"error": "Exam not found or not available"}), 404
        
        # Check if already registered
        registered = db.exam_registration.find_one({
            "exam_id": exam["_id"],
            "user_id": g.current_user["_id"]
        }) is not None
        
        return jsonify({
            "_id": str(exam["_id"]),
            "title": exam["title"],
            "description": exam.get("description", ""),
            "code": exam["code"],
            "start_time": exam.get("start_time"),
            "end_time": exam.get("end_time"),
            "duration_seconds": exam.get("duration_seconds", 3600),
            "question_count": exam.get("question_count", 0),
            "registered": registered
        }), 200
        
    except Exception as e:
        current_app.logger.exception("Check exam by code error")
        return jsonify({"error": "Failed to check exam"}), 500
