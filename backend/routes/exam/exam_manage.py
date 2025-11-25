from flask import Blueprint, request, jsonify, current_app, g 
from backend.utils.exam_validation import validate_exam_payload, validate_question_payload
from backend.models.exam import exam_doc
from backend.models.question import question_doc
from backend.extensions import limiter
from datetime import datetime 
from bson import ObjectId
from backend.middleware.auth import token_required
from backend import mongo

exam_manage_bp = Blueprint("exam_manage", __name__, url_prefix="/api/exam/manage")

def require_exam_owner(exam):
    return str(exam.get("owner_id")) == str(g.current_user["_id"])

@exam_manage_bp.route("/create", methods=["POST"])
@token_required
@limiter.limit('5 per minute')
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
@limiter.limit('10 per minute')
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
@limiter.limit('10 per minute')
def add_questions(exam_id):
    """
    Add multiple questions in one request.
    Returns detailed info about which ones succeeded or failed.
    """
    try:
        data = request.get_json() or {}
        questions = data.get("questions", [])

        if not isinstance(questions, list) or not questions:
            return jsonify({"error": "questions must be a non-empty list"}), 400

        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404

        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403

        inserted_ids = []
        failed = []

        for idx, qdata in enumerate(questions, start=1):
            qdata["exam_id"] = exam_id

            # Normalize fields
            qdata["prompt"] = qdata.pop("question", qdata.get("prompt"))
            qdata["answer_key"] = qdata.pop("correct_answer", qdata.get("answer_key"))

            ok, err = validate_question_payload(qdata)
            if not ok:
                failed.append({
                    "index": idx,
                    "prompt": qdata.get("prompt"),
                    "error": err
                })
                continue

            try:
                q = question_doc(
                    exam_id=exam["_id"],
                    qtype=qdata["type"],
                    prompt=qdata["prompt"],
                    options=qdata.get("options"),
                    answer_key=qdata.get("answer_key"),
                    points=int(qdata.get("points", 1)),
                    media=qdata.get("media"),
                    shuffle_options=qdata.get("shuffle_options", True),
                    meta=qdata.get("meta", {})  # for custom type info
                )
                res = db.exam_questions.insert_one(q)
                inserted_ids.append(str(res.inserted_id))

            except Exception as inner_e:
                failed.append({
                    "index": idx,
                    "prompt": qdata.get("prompt"),
                    "error": str(inner_e)
                })

        # Update question count
        if inserted_ids:
            db.exams.update_one(
                {"_id": exam["_id"]},
                {"$inc": {"question_count": len(inserted_ids)}, "$set": {"updated_at": datetime.utcnow()}}
            )

        return jsonify({
            "message": "Bulk question upload completed",
            "inserted_count": len(inserted_ids),
            "failed_count": len(failed),
            "inserted_ids": inserted_ids,
            "failed": failed
        }), 207 if failed else 201  # Multi-Status for partial success

    except Exception as e:
        current_app.logger.exception("Add questions upload error")
        return jsonify({"error": "Failed to add questions", "details": str(e)}), 500


exam_manage_bp.route("/<exam_id>/update", methods=["PUT", "PATCH"])
@token_required
@limiter.limit("10 per minute")
def update_exam(exam_id):
    """
    Update an exam. only allowed for the owner.
    Accepts partial updates.
    body: {title?, description}
    """
    try:
        data = request.get_json() or {}
        if not data:
            return jsonify({"error": "Request body is empty"}), 400
        
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"errror": "Exam not found"}), 404
        
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbideen"}), 403
        
        update_fields = {}
        
        if "title" in data:
            update_fields["title"] = data["title"]
            
        if "description" in data:
            update_fields["description"] = data["description"]
            
        if "start_time" in data:
            update_fields["start_time"] = data["start_time"]
            
        if "end_time" in data:
            update_fields["end_time"] = data["end_time"]
            
        if "duration_seconds" in data:
            update_fields["duration_seconds"] = int(data["duration_seconds"])
            
        if "code" in data:
            new_code = data["code"].strip()
            exist = db.exams.find_one({"code": new_code, "_id": {"$ne": exam["_id"]}})
            if exist:
                return jsonify({"error": 'Exam code already taken'})
            update_fields["code"] = new_code 
            if "settings" in data:
                update_fields["settings"] = data["settings"]
                
            update_fields["updated_at"] = datetime.utcnow()
            
            if not update_fields:
                return jsonify({"error": "No valid field to update"}), 400
            
            db.exams.update_one({"_id": exam["_id"]}, {"$set": update_fields})
            
            return jsonify({"message": "Exam updated successfully"}), 200
        
    except Exception as e:
        current_app.logger.exception("Update exam error")
        return jsonify({"error": "failed to update exam", "details": str(e)}), 500
    
    
    
@exam_manage_bp.route("/<exam_id>/delete"w, methods=["DELETE"])
@token_required
@limiter.limit("10 per minute")
def delete_exam(exam_id):
    """
    Delete an exam and all its associated questions.
    Only the owner can delete
    """
    try:
        db = current_app.mongo.db
        
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403
        
        db.exam_questions.delete_many({"exam_id": exam["_id"]})
        
        db.exams.delete_one({"_id": exam['_id']})
        
        return jsonify({"message": "Exam deleted successsufully"}), 200
    
    except Exception as e:
        current_app.logger.exception("Deleted exam error")
        return jsonify({"error": "Failed to delete exam", "details": str(e)}), 500