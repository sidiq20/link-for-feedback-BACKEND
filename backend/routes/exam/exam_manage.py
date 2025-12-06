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


@exam_manage_bp.route("/list", methods=["GET"])
@token_required
def list_exams():
    """List all exams created by the current user."""
    try:
        db = current_app.mongo.db
        exams = list(db.exams.find({"owner_id": g.current_user["_id"]}).sort("created_at", -1))
        for exam in exams:
            exam["_id"] = str(exam["_id"])
            exam["owner_id"] = str(exam["owner_id"])
        return jsonify({"exams": exams}), 200
    except Exception as e:
        current_app.logger.exception("List exams error")
        return jsonify({"error": "Failed to list exams"}), 500


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
    
    


@exam_manage_bp.route("/<exam_id>/questions", methods=["GET"])
@token_required
def get_exam_questions(exam_id):
    """
    Get all questions for an exam (for exam details page).
    Returns decrypted questions with full details for examiners.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        # Check permissions (owner or examiner)
        is_owner = str(exam.get("owner_id")) == str(g.current_user["_id"])
        is_examiner = False
        if not is_owner:
            for ex in exam.get("examiners", []):
                if isinstance(ex, dict) and str(ex.get("_id")) == str(g.current_user["_id"]):
                    is_examiner =  True
                    break
        
        if not (is_owner or is_examiner):
            return jsonify({"error": "Forbidden"}), 403
        
        # Fetch all questions
        questions = list(db.exam_questions.find({"exam_id": ObjectId(exam_id)}))
        
        # Format questions (prompt and options are stored as plain text, not encrypted)

        from backend.utils.security import decrypt_answer

        formatted_questions = []
        
        for q in questions:
            formatted_q = {
                "_id": str(q["_id"]),
                "type": q["type"],
                "points": q.get("points", 1),
                "text": q.get("prompt", ""),  # Use 'prompt' field, not 'text'

                "options": q.get("options"),  # Options are stored as plain text

                "correct_answer": None,
                "media": q.get("media"),
                "shuffle_options": q.get("shuffle_options", False),
                "allow_partial": q.get("allow_partial", False),
            }
            
            # Decrypt correct answer for examiners (answer_key_encrypted is the encrypted field)

            if q.get("answer_key_encrypted"):

                try:

                    formatted_q["correct_answer"] = decrypt_answer(q["answer_key_encrypted"])

                except Exception as e:

                    current_app.logger.warning(f"Failed to decrypt answer for question {q['_id']}: {e}")

                    formatted_q["correct_answer"] = None

            formatted_questions.append(formatted_q)
        
        return jsonify(formatted_questions), 200
        
    except Exception as e:
        current_app.logger.exception("Get exam questions error")
        return jsonify({"error": "Failed to fetch questions", "details": str(e)}), 500
    

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
            "inserted_ids": inserted_ids,
            "failed": failed
        }), 201
    except Exception as e:
        current_app.logger.exception("Failed to add questions")
        return jsonify({"error": "Failed to add questions", "details": str(e)}), 500

@exam_manage_bp.route("/<exam_id>/update", methods=["PUT"])
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
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403
        
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
                return jsonify({"error": 'Exam code already taken'}), 400
            update_fields["code"] = new_code
            
        if "settings" in data:
            update_fields["settings"] = data["settings"]
            
        if not update_fields:
            return jsonify({"error": "No valid field to update"}), 400
            
        update_fields["updated_at"] = datetime.utcnow()
        db.exams.update_one({"_id": exam["_id"]}, {"$set": update_fields})
        
        return jsonify({"message": "Exam updated successfully"}), 200
        
    except Exception as e:
        current_app.logger.exception("Update exam error")
        return jsonify({"error": "failed to update exam", "details": str(e)}), 500
    
    
    
@exam_manage_bp.route("/<exam_id>/delete", methods=["DELETE"])
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


@exam_manage_bp.route("/<exam_id>", methods=["GET"])
@token_required
def get_exam_details(exam_id):
    """
    Fetch full exam info (for editors/owners).
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        # Check permissions (owner or invited examiner with view permissions)
        # For simplicity, using require_exam_owner or checking examiners list
        is_owner = str(exam.get("owner_id")) == str(g.current_user["_id"])
        is_examiner = False
        if not is_owner:
            for ex in exam.get("examiners", []):
                if isinstance(ex, dict) and str(ex.get("_id")) == str(g.current_user["_id"]):
                    is_examiner = True
                    break
        
        if not (is_owner or is_examiner):
            return jsonify({"error": "Forbidden"}), 403

        exam["_id"] = str(exam["_id"])
        exam["owner_id"] = str(exam["owner_id"])
        # Convert other ObjectIds if necessary
        
        return jsonify(exam), 200
    except Exception as e:
        current_app.logger.exception("Get exam details error")
        return jsonify({"error": "Failed to fetch exam details"}), 500


@exam_manage_bp.route("/<exam_id>/settings", methods=["PUT"])
@token_required
@limiter.limit("10 per minute")
def update_exam_settings(exam_id):
    """
    Update specific settings (time, shuffle, retake, etc.)
    Body: { settings: { ... } }
    """
    try:
        db = current_app.mongo.db
        data = request.get_json() or {}
        settings = data.get("settings")
        
        if settings is None:
             return jsonify({"error": "No settings provided"}), 400

        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403

        db.exams.update_one(
            {"_id": exam["_id"]},
            {"$set": {"settings": settings, "updated_at": datetime.utcnow()}}
        )
        return jsonify({"message": "Settings updated"}), 200
    except Exception as e:
        current_app.logger.exception("Update settings error")
        return jsonify({"error": "Failed to update settings"}), 500


@exam_manage_bp.route("/<exam_id>/questions/<qid>", methods=["PUT"])
@token_required
@limiter.limit("10 per minute")
def update_question(exam_id, qid):
    """
    Update a specific question.
    """
    try:
        db = current_app.mongo.db
        data = request.get_json() or {}
        
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        if not require_exam_owner(exam):
             return jsonify({"error": "Forbidden"}), 403

        # Validate payload if necessary (reuse validate_question_payload)
        # For now, just update fields provided
        update_fields = {}
        if "prompt" in data: update_fields["prompt"] = data["prompt"]
        if "options" in data: update_fields["options"] = data["options"]
        if "answer_key" in data: update_fields["answer_key"] = data["answer_key"]
        if "points" in data: update_fields["points"] = int(data["points"])
        if "media" in data: update_fields["media"] = data["media"]
        if "type" in data: update_fields["type"] = data["type"]
        
        if not update_fields:
            return jsonify({"error": "No fields to update"}), 400

        result = db.exam_questions.update_one(
            {"_id": ObjectId(qid), "exam_id": ObjectId(exam_id)},
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            return jsonify({"error": "Question not found"}), 404

        return jsonify({"message": "Question updated"}), 200
    except Exception as e:
        current_app.logger.exception("Update question error")
        return jsonify({"error": "Failed to update question"}), 500


@exam_manage_bp.route("/<exam_id>/questions/<qid>", methods=["DELETE"])
@token_required
@limiter.limit("10 per minute")
def delete_question(exam_id, qid):
    """
    Remove a specific question.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        if not require_exam_owner(exam):
            return jsonify({"error": "Forbidden"}), 403

        result = db.exam_questions.delete_one({"_id": ObjectId(qid), "exam_id": ObjectId(exam_id)})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Question not found"}), 404
            
        # Update question count
        db.exams.update_one(
            {"_id": exam["_id"]},
            {"$inc": {"question_count": -1}, "$set": {"updated_at": datetime.utcnow()}}
        )

        return jsonify({"message": "Question deleted"}), 200
    except Exception as e:
        current_app.logger.exception("Delete question error")
        return jsonify({"error": "Failed to delete question"}), 500


@exam_manage_bp.route("/<exam_id>/clone", methods=["POST"])
@token_required
@limiter.limit("5 per minute")
def clone_exam(exam_id):
    """
    Duplicate exam and its questions.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        # Anyone can clone? Or only owner? Let's assume anyone logged in can clone a public/shared exam, 
        # or at least the owner can clone their own. For now, enforce owner or maybe just token_required.
        # Let's enforce owner for now to be safe, or allow if it's a template.
        # Going with owner only for now based on "Missing but required" context usually implying management.
        if not require_exam_owner(exam):
             return jsonify({"error": "Forbidden"}), 403

        new_exam = exam.copy()
        del new_exam["_id"]
        new_exam["title"] = f"{exam.get('title')} (Copy)"
        new_exam["code"] = f"{exam.get('code')}-{datetime.utcnow().timestamp()}" # Temporary unique code
        new_exam["created_at"] = datetime.utcnow()
        new_exam["updated_at"] = datetime.utcnow()
        new_exam["status"] = "draft"
        new_exam["owner_id"] = g.current_user["_id"]
        new_exam["invited_examiners"] = [] # Don't clone invites
        new_exam["examiners"] = []
        
        res = db.exams.insert_one(new_exam)
        new_exam_id = res.inserted_id
        
        # Clone questions
        questions = list(db.exam_questions.find({"exam_id": ObjectId(exam_id)}))
        if questions:
            for q in questions:
                del q["_id"]
                q["exam_id"] = new_exam_id
            db.exam_questions.insert_many(questions)

        return jsonify({"message": "Exam cloned", "new_exam_id": str(new_exam_id)}), 201
    except Exception as e:
        current_app.logger.exception("Clone exam error")
        return jsonify({"error": "Failed to clone exam"}), 500