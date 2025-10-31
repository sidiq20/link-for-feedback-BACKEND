from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from backend.models.result import result_doc
from backend.models.question import hash_answer, normalize_answer
from datetime import datetime, timedelta
from bson import ObjectId
import uuid

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
            'updated_at': datetime.utcnow()
        }
        db.exam_sessions.insert_one(session)
        
        res = result_doc(exam_id=exam['_id'], session_id=session['_id'], student_id=g.current_user['_id'], final_score=None, graded=False)
        db.exam_results.insert_one(res)
        
        duration_seconds = exam.get('duration_seconds', 3600)
        expire_at = datetime.utcnow() + timedelta(seconds=duration_seconds)
        
        ws_url = current_app.config.get('WS_BASE_URL', "") + f"/ws/exam/{str(session['_id'])}"
        return jsonify({
            'message': 'Session started',
            'session_id': str(session['_id']),
            'expire_at': expire_at.isoformat(),
            'ws_url': ws_url
        }), 200
    except Exception as e:
        current_app.logger.exception('Start exam error')
        return jsonify({'error': 'Failed to start exam', 'details': str(e)})
    
@exam_take_bp.route('/answer', methods=['POST'])
@token_required
def save_answer():
    """
    Body: { session_id, question_id, answer, client_save_id? }
    Saves (auto-save) an answer. Light validation and append-only
    """
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        question_id = data.get('question_id')
        answer = data.get('answer')
        
        if not session_id or not question_id:
            return jsonify({'error': 'session_id and question_id required'}), 400
        
        db = current_app.mongo.db
        session = db.exam_sessions.find_one({'_id': ObjectId(session_id), 'user_id': ObjectId(g.current_user['_id'])})
        if not session:
            return jsonify({'error': 'Session not found or not yours'}), 404
        
        ans_doc = {
            '_id': ObjectId(),
            'session_id': session['_id'],
            'question_id': ObjectId(question_id),
            'answer': answer,
            'saved_at': datetime.utcnow(),
            'is_final': False 
        }
        db.exam_answers.insert_one(ans_doc)
        db.exam_sessions.update_one({'_id': session['_id']}, {'$set': {'updated_at': datetime.utcnow()}})
        return jsonify({'saved': True, 'saved_at': ans_doc['saved_at'].isoformat()}), 200
    
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