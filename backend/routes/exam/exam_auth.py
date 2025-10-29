from flask import Blueprint, request, jsonify, current_app, g 
from backend.utils.exam_validation import sanitize_student_id, is_valid_objectid, is_valid_student_id, generate_student_id
from bson import ObjectId
from datetime import datetime
from backend.middleware.auth import token_required
from backend.extensions import mongo
from backend.models.exam_registration import registration_doc
from backend.utils.mailer import send_email


exam_auth_bp = Blueprint("exam_auth", __name__, url_prefix="/api/exam/auth")

@exam_auth_bp.route("/register", methods=["POST"])
@token_required
def register_for_exam():
    """
    Registers the current user for an exam.
    Automatically assigns a student_id if the user doesn't have one.
    """
    try:
        data = request.get_json() or {}
        exam_code = (data.get("exam_code") or "").strip()

        if not exam_code:
            return jsonify({"error": "exam_code is required"}), 400

        db = current_app.mongo.db
        users = db.users
        user_id = ObjectId(g.current_user["_id"])

        # Fetch user record
        user = users.find_one({"_id": user_id})
        if not user:
            return jsonify({"error": "User not found"}), 404

        student_id = user.get("student_id")

        # --- Auto-generate student ID if missing ---
        if not student_id:
            while True:
                student_id = generate_student_id()
                if not users.find_one({"student_id": student_id}):
                    break

            users.update_one({"_id": user_id}, {"$set": {"student_id": student_id}})
            current_app.logger.info(f"Assigned new student_id {student_id} to user {user_id}")

        # --- Validate format ---
        if not is_valid_student_id(student_id):
            return jsonify({"error": "Invalid student ID format"}), 400

        # --- Find exam ---
        exam = db.exams.find_one({
            "code": exam_code,
            "status": {"$in": ["published", "draft", "closed"]}
        })
        if not exam:
            return jsonify({"error": "Exam not found"}), 404

        # --- Prevent duplicate registration ---
        existing = db.exam_registration.find_one({
            "exam_id": exam["_id"],
            "user_id": user_id
        })
        if existing:
            return jsonify({
                "message": "Already registered",
                "registration_id": str(existing["_id"])
            }), 200

        # --- Create registration record ---
        reg = registration_doc(
            exam_id=exam["_id"],
            user_id=user_id,
            student_id=student_id
        )
        res = db.exam_registration.insert_one(reg)

        return jsonify({
            "message": "Registration successful",
            "student_id": student_id,
            "registration_id": str(res.inserted_id)
        }), 201

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
        
        
@exam_auth_bp.route("/create-student-id", methods=["POST"])
@token_required
def create_student_id():
    """
    Allows a logged-in user to create (or retrieve) their student_id.
    """
    try:
        db = current_app.mongo.db
        user_id = ObjectId(g.current_user["_id"])
        users = db.users  # your users collection

        # check if user already has a student ID
        existing_user = users.find_one({"_id": user_id}, {"student_id": 1})
        if existing_user and existing_user.get("student_id"):
            return jsonify({
                "message": "Student ID already exists",
                "student_id": existing_user["student_id"]
            }), 200

        # generate and ensure uniqueness
        while True:
            student_id = generate_student_id()
            if not users.find_one({"student_id": student_id}):
                break

        # update user profile
        users.update_one({"_id": user_id}, {"$set": {"student_id": student_id}})

        return jsonify({
            "message": "Student ID created successfully",
            "student_id": student_id
        }), 201

    except Exception as e:
        current_app.logger.exception("Error creating student ID")
        return jsonify({"error": "Failed to create student ID", "details": str(e)}), 500
