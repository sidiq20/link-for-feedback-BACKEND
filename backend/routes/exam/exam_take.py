from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from backend.models.result import result_doc
from backend.models.question import hash_answer, normalize_answer
from datetime import datetime, timedelta
from bson import ObjectId
import uuid
import jwt

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
def submit_session():
    '''
    Body: { session_id }
    Final submission. Marks session submitted and triggers grading for auto-gradable items.
    '''
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400
        
        db = current_app.mongo.db
        session = db.exam_sessions.find_one({"_id": ObjectId(session_id), 'user_id': ObjectId(g.current_user['_id'])})
        if not session:
            return jsonify({'error': 'Session not found or not yours'}), 404
        
        # mark session as submitted
        db.exam_sessions.update_one({'_id': session['_id']}, {'$set': {'status': 'submitted', 'ended_at': datetime.utcnow(), 'updated_at': datetime.utcnow()}})
        
        # mark result status
        db.exam_results.update_one({'session_id': session['_id']}, {'$set': {'status': 'submitted', 'ended_at': datetime.utcnow(), 'updated_at': datetime.utcnow()}})
        
        # queue grading job - for now we do simple inline autograde for MCQ
        # fetch answers and grade MCQ
        exam_id = session['exam_id']
        questions = list(db.exam_questions.find({'exam_id': exam_id}))
        answers_docs = list(db.exam_answers.find({'session_id': session['_id']}))
        
        # map latest answer per question_id
        latest = {}
        for a in answers_docs:
            qid = str(a['question_id'])
            if qid not in latest or a['saved_at'] > latest[qid]['saved_at']:
                latest[qid] = a 
                
        total_score = 0
        possible = 0
        for q in questions:
            qid = str(q['_id'])
            possible += q.get('points', 1)
            if q['type'] == 'mcq' and qid in latest:
                given = latest[qid]['answer']
                stored_hash = q.get('answer_key')
                if given is not None and stored_hash is not None:
                    # Hash the user's answer and compare with stored hash
                    given_hash = hash_answer(given)
                    if given_hash == stored_hash:
                        total_score += q.get('points', 1)
                # text answers marked for manual review (skip)
                    
        
        # Update result doc
        db.exam_results.update_one({'session_id': session['_id']}, {'$set': {'final_score': total_score, 'graded': True, 'status': 'graded', 'updated_at': datetime.utcnow()}})
        
        return jsonify({'message': 'Submitted', 'final_score': total_score, 'possible': possible})
    
    except Exception as e:
        current_app.logger.exception('Submit session error')
        return jsonify({'error': 'submission failed', 'details': str(e)}), 500