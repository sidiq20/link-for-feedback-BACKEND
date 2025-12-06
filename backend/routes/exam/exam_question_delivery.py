from flask import Blueprint, jsonify, current_app, g
from backend.utils.ansers import load_correct_answer
from bson import ObjectId
from backend.middleware.auth import token_required
from backend.extensions import mongo, limiter


exam_question_delivery_bp = Blueprint('exam_devliver', __name__, url_prefix='/api/exam_question_delivery')

@exam_question_delivery_bp.route('/question/<exam_id>')
@token_required
def get_exam_question(exam_id):
    exam = mongo.db.exams.find_one({'_id': ObjectId(exam_id)})
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    raw_qs = list(mongo.db.questions.find({'exam_id': ObjectId(exam_id)}))
    
    questions = []
    for q in raw_qs:
        q["_id"] = str(q["_id"])
        q["exam_id"] = str(q["exam_id"])
        
        q.pop("answer_key_hash", None)
        
        if g.user["role"] == 'staff':
            try:
                q["answer_key"] = load_correct_answer(q.get("answer_key_encrypted"))
            except Exception:
                q["answer_key"] = None 
        else:
            q.pop("answer_key_encrypted", None)
            
        questions.append(q)
        
    return jsonify({'questions': questions}), 200


@exam_question_delivery_bp.route('/review/<session_id>', methods=['GET'])
@token_required
def review_session_questions(session_id):
    """
    Return delivered question order for a session.
    """
    try:
        db = current_app.mongo.db
        # Verify session belongs to user
        session = db.exam_sessions.find_one({
            '_id': ObjectId(session_id),
            'user_id': ObjectId(g.current_user['_id'])
        })
        if not session:
            return jsonify({'error': 'Session not found'}), 404

        questions = list(db.exam_questions.find({'exam_id': session['exam_id']}))
        
        results = []
        for q in questions:
            results.append({
                'question_id': str(q['_id']),
                'type': q['type'],
                'prompt': q.get('prompt') or q.get('text'),
            })
            
        return jsonify({'questions': results}), 200
    except Exception as e:
        current_app.logger.exception("review_session error")
        return jsonify({'error': str(e)}), 500


@exam_question_delivery_bp.route('/flag', methods=['POST'])
@token_required
def flag_question():
    """
    Mark a question as flagged by student.
    Body: { session_id, question_id, flagged: bool }
    """
    try:
        db = current_app.mongo.db
        data = request.get_json() or {}
        session_id = data.get('session_id')
        question_id = data.get('question_id')
        flagged = data.get('flagged', True)
        
        if not session_id or not question_id:
            return jsonify({'error': 'session_id and question_id required'}), 400
            
        # Verify ownership
        session = db.exam_sessions.find_one({
            '_id': ObjectId(session_id),
            'user_id': ObjectId(g.current_user['_id'])
        })
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        db.exam_answers.update_one(
            {'session_id': ObjectId(session_id), 'question_id': ObjectId(question_id)},
            {
                '$set': {'flagged': flagged, 'updated_at': datetime.utcnow()},
                '$setOnInsert': {
                    '_id': ObjectId(),
                    'exam_id': session['exam_id'],
                    'user_id': session['user_id'],
                    'answer': None
                }
            },
            upsert=True
        )
        
        return jsonify({'message': 'Flag updated'}), 200
    except Exception as e:
        current_app.logger.exception("flag_question error")
        return jsonify({'error': str(e)}), 500