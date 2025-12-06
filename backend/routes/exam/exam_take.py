from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from backend.models.result import result_doc
from backend.models.question import hash_answer, normalize_answer
from datetime import datetime, timedelta
from bson import ObjectId
import uuid
import jwt
from backend.extensions import limiter

from backend.routes.exam.exam_socket import push_progress_update

exam_take_bp = Blueprint("exam_take", __name__, url_prefix="/api/exam/take")

@exam_take_bp.route("/<exam_id>/start", methods=["POST"])
@token_required
def start_exam(exam_id):
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({"_id": ObjectId(exam_id), "status": "published"})
        if not exam:
            return jsonify({"error": "Exam not available"}), 404

        reg = db.exam_registration.find_one({"exam_id": exam["_id"], "user_id": ObjectId(g.current_user["_id"])})
        if not reg:
            return jsonify({"error": "User not registered for this exam"}), 403

        duration_seconds = exam.get('duration_seconds', 3600)
        expire_at = datetime.utcnow() + timedelta(seconds=duration_seconds)

        session = {
            "_id": ObjectId(),
            "exam_id": exam["_id"],
            "user_id": ObjectId(g.current_user["_id"]),
            "student_id": reg["student_id"],
            "started_at": datetime.utcnow(),
            "status": "in_progress",
            "violation_count": 0,
            "device_fingerprint": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "expire_at": expire_at
        }
        # insert only once
        db.exam_sessions.insert_one(session)

        res = result_doc(
            exam_id=exam['_id'],
            session_id=session['_id'],
            student_id=reg['student_id'],
            user_id=g.current_user['_id'],
            final_score=None,
            graded=False
        )
        db.exam_results.insert_one(res)

        # create a short-lived WS token for the client to use when connecting to socket
        ws_payload = {
            "user_id": str(g.current_user["_id"]),
            "session_id": str(session["_id"]),
            "iat": datetime.utcnow().timestamp()
        }
        ws_token = jwt.encode(ws_payload, current_app.config["SECRET_KEY"], algorithm="HS256")
        ws_base = current_app.config.get('WS_BASE_URL', "")
        # ws_url example: wss://yourdomain/ws/exam?token=...&session_id=...
        ws_url = f"{ws_base}/socket.io/?token={ws_token}&session_id={str(session['_id'])}"

        return jsonify({
            'message': 'Session started',
            'session_id': str(session['_id']),
            'expire_at': expire_at.isoformat(),
            'ws_token': ws_token,
            'ws_url': ws_url
        }), 200
    except Exception as e:
        current_app.logger.exception('Start exam error')
        return jsonify({'error': 'Failed to start exam', 'details': str(e)}), 500


@exam_take_bp.route('/answer', methods=['POST'])
@token_required
def save_answer():
    """
    Saves one or multiple answers.
    Body (single): { session_id, question_id, answer }
    Body (bulk): { session_id, answers: [{ question_id, answer }, ...] }
    """
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400

        db = current_app.mongo.db
        session = db.exam_sessions.find_one(
            {'_id': ObjectId(session_id), 'user_id': ObjectId(g.current_user['_id'])}
        )
        if not session:
            return jsonify({'error': 'Session not found or not yours'}), 404

        # Normalize for both single and multiple answers
        answers_input = []
        if 'answers' in data:
            answers_input = data['answers']
        elif 'question_id' in data:
            answers_input = [{'question_id': data['question_id'], 'answer': data['answer']}]
        else:
            return jsonify({'error': 'No answers provided'}), 400

        saved_answers = []
        for entry in answers_input:
            qid = entry.get('question_id')
            raw_answer = entry.get('answer')
            if not qid:
                continue

            question = db.exam_questions.find_one({'_id': ObjectId(qid)})
            if not question:
                continue

            qtype = question.get('type')
            answer = normalize_answer(raw_answer)

            # --- Type-specific normalization ---
            if qtype == 'mcq':
                if isinstance(answer, list):
                    answer = sorted([normalize_answer(a) for a in answer])
                else:
                    answer = normalize_answer(answer)

            elif qtype in ('fill_blank', 'text', 'math', 'image_label'):
                if isinstance(answer, str):
                    answer = answer.strip().lower()

            elif qtype == 'boolean':
                if isinstance(answer, str):
                    answer = answer.lower() in ['true', '1', 'yes']
                elif isinstance(answer, (int, float)):
                    answer = bool(answer)

            elif qtype == 'file_upload':
                if not isinstance(answer, dict) or 'url' not in answer:
                    return jsonify({'error': 'file_upload answer must include url'}), 400

            elif qtype == 'match':
                if isinstance(answer, dict):
                    answer = {k.strip().lower(): v.strip().lower() for k, v in sorted(answer.items())}

            elif qtype == 'code':
                if isinstance(answer, str):
                    answer = answer.strip()

            # --- Save (upsert) each answer ---
            db.exam_answers.update_one(
                {'session_id': session['_id'], 'question_id': ObjectId(qid)},
                {
                    '$set': {
                        'answer': answer,
                        'saved_at': datetime.utcnow(),
                        'is_final': False
                    },
                    '$setOnInsert': {'_id': ObjectId()}
                },
                upsert=True
            )
            saved_answers.append({'question_id': str(qid), 'normalized_answer': answer})

        # Update session timestamp
        db.exam_sessions.update_one(
            {'_id': session['_id']},
            {'$set': {'updated_at': datetime.utcnow()}}
        )

        # Emit progress update once
        total_questions = db.exam_questions.count_documents({'exam_id': session['exam_id']})
        answered_count = db.exam_answers.count_documents({'session_id': session['_id']})
        percent = int((answered_count / max(total_questions, 1)) * 100)

        push_progress_update(session_id, {
            'session_id': session_id,
            'answered': answered_count,
            'total': total_questions,
            'percent': percent,
            'ts': datetime.utcnow().isoformat()
        })

        return jsonify({
            'saved': True,
            'count': len(saved_answers),
            'answers': saved_answers,
            'progress': {'answered': answered_count, 'total': total_questions, 'percent': percent}
        }), 200

    except Exception as e:
        current_app.logger.exception('Save answer error')
        return jsonify({'error': 'Failed to save answer', 'details': str(e)}), 500

    
@exam_take_bp.route('/submit', methods=['POST'])
@token_required
@limiter.limit('10 per minute')
def submit_session():
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400

        db = current_app.mongo.db
        session = db.exam_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": ObjectId(g.current_user["_id"])
        })
        if not session:
            return jsonify({'error': 'Session not found or not yours'}), 404

        db.exam_sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {
                "status": "submitted",
                "ended_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }}
        )

        db.exam_results.update_one(
            {"session_id": session["_id"]},
            {"$set": {
                "status": "submitted",
                "submitted_at": datetime.utcnow()
            }}
        )

        exam_id = session["exam_id"]
        questions = list(db.exam_questions.find({"exam_id": exam_id}))
        answers_docs = list(db.exam_answers.find({"session_id": session["_id"]}))

        # map answers
        latest = {}
        for a in answers_docs:
            qid = str(a["question_id"])
            if qid not in latest or a["saved_at"] > latest[qid]["saved_at"]:
                latest[qid] = a

        total_score = 0
        possible_score = 0
        detailed_results = []

        from backend.models.question import decrypt_value, normalize_answer

        for q in questions:
            qid = str(q["_id"])
            qtype = q["type"]
            points = q.get("points", 1)
            possible_score += points

            encrypted_key = q.get("answer_key")
            correct_answer = decrypt_value(encrypted_key) if encrypted_key else None
            user_answer = latest.get(qid, {}).get("answer")

            auto_score = 0
            needs_manual = False

            if qtype == "mcq" and correct_answer is not None:
                corr = normalize_answer(correct_answer)
                given = normalize_answer(user_answer)

                if isinstance(corr, list):
                    corr = sorted(corr)
                if isinstance(given, list):
                    given = sorted(given)

                if corr == given:
                    auto_score = points
                elif q.get("allow_partial") and isinstance(corr, list) and isinstance(given, list):
                    correct_hits = len(set(corr) & set(given))
                    auto_score = (correct_hits / len(corr)) * points

            elif qtype == "boolean":
                if str(user_answer).lower() == str(correct_answer).lower():
                    auto_score = points

            elif qtype in ("text", "fill_blank"):
                # crude auto grading; can be replaced with fuzzy matching or embeddings later
                if normalize_answer(user_answer) == normalize_answer(correct_answer):
                    auto_score = points
                else:
                    needs_manual = True

            elif qtype in ("code", "essay", "file_upload"):
                needs_manual = True

            # Save question_result entry
            detailed_results.append({
                "question_id": qid,
                "type": qtype,
                "user_answer": user_answer,
                "correct_answer": None,     # Hide from student
                "awarded": auto_score,
                "possible": points,
                "needs_manual": needs_manual
            })

            total_score += auto_score

        # Update main result record
        db.exam_results.update_one(
            {"session_id": session["_id"]},
            {"$set": {
                "auto_score": total_score,
                "possible_score": possible_score,
                "detailed": detailed_results,
                "graded": not any(r["needs_manual"] for r in detailed_results),
                "updated_at": datetime.utcnow()
            }}
        )

        return jsonify({
            "message": "Submitted successfully",
            "auto_score": total_score,
            "possible_score": possible_score,
            "needs_manual_review": any(r["needs_manual"] for r in detailed_results)
        }), 200

    except Exception as e:
        current_app.logger.exception("Submit grading error")
        return jsonify({'error': 'Failed to submit and grade', 'details': str(e)}), 500
  
@exam_take_bp.route('/<exam_id>/question', methods=["GET"])
@token_required
def get_questions(exam_id):
    try:
        db = current_app.mongo.db
        
        exam = db.exams.find_one({'_id': ObjectId(exam_id), "status": "published"})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
        
        session = db.exam_sessions.find_one({
            'exam_id': ObjectId(exam_id),
            'user_id': ObjectId(g.current_user['_id']),
            'status': {'$in': ['in_progress', 'submitted']}
        })
        
        if not session:
            return jsonify({'error': 'No active session found'}), 403
        
        questions = list(db.exam_questions.find({'exam_id': ObjectId(exam_id)}))
        
        delivered = []
        # from backend.models.question import decrypt_value
        
        for q in questions:
            # Prompt and options are stored as plain text
            decrypted_text = q.get("prompt", "")
            decrypted_options = q.get("options")
            
            delivered.append({
                "question_id": str(q["_id"]),
                "type": q["type"],
                "points": q.get("points", 1),
                "text": decrypted_text,
                "options": decrypted_options,
                "media": q.get("media"),
                "shuffle": q.get("shuffle_options", False),
                "allow_partial": q.get("allow_partial", False),
            })
            
        return jsonify({
            "session_id": str(session["_id"]),
            "questions": delivered
        }), 200

    except Exception as e:
        current_app.logger.exception("Failed to fetch questions")
        return jsonify({"error": "Failed to fetch questions", "details": str(e)}), 500


@exam_take_bp.route('/session/<session_id>', methods=['GET'])
@token_required
def get_session_state(session_id):
    """
    Get current session state.
    """
    try:
        db = current_app.mongo.db
        session = db.exam_sessions.find_one({
            '_id': ObjectId(session_id),
            'user_id': ObjectId(g.current_user['_id'])
        })
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        session['_id'] = str(session['_id'])
        session['exam_id'] = str(session['exam_id'])
        session['user_id'] = str(session['user_id'])
        session['student_id'] = str(session['student_id']) if session.get('student_id') else None
        
        return jsonify(session), 200
    except Exception as e:
        current_app.logger.exception("get_session_state error")
        return jsonify({'error': str(e)}), 500


@exam_take_bp.route('/session/<session_id>/pause', methods=['POST'])
@token_required
def pause_session(session_id):
    """
    Pause session if allowed.
    """
    try:
        db = current_app.mongo.db
        session = db.exam_sessions.find_one({
            '_id': ObjectId(session_id),
            'user_id': ObjectId(g.current_user['_id'])
        })
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        # Check if exam allows pausing? For now assume yes or check settings
        exam = db.exams.find_one({"_id": session["exam_id"]})
        if not exam or not exam.get("settings", {}).get("allow_pause", True):
             return jsonify({'error': 'Pausing not allowed'}), 403
             
        if session['status'] != 'in_progress':
            return jsonify({'error': 'Session not in progress'}), 400
            
        db.exam_sessions.update_one(
            {'_id': ObjectId(session_id)},
            {'$set': {'status': 'paused', 'updated_at': datetime.utcnow()}}
        )
        
        return jsonify({'message': 'Session paused'}), 200
    except Exception as e:
        current_app.logger.exception("pause_session error")
        return jsonify({'error': str(e)}), 500


@exam_take_bp.route('/session/<session_id>/resume', methods=['POST'])
@token_required
def resume_session(session_id):
    """
    Resume session.
    """
    try:
        db = current_app.mongo.db
        session = db.exam_sessions.find_one({
            '_id': ObjectId(session_id),
            'user_id': ObjectId(g.current_user['_id'])
        })
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        if session['status'] != 'paused':
            return jsonify({'error': 'Session not paused'}), 400
            
        db.exam_sessions.update_one(
            {'_id': ObjectId(session_id)},
            {'$set': {'status': 'in_progress', 'updated_at': datetime.utcnow()}}
        )
        
        return jsonify({'message': 'Session resumed'}), 200
    except Exception as e:
        current_app.logger.exception("resume_session error")
        return jsonify({'error': str(e)}), 500