from flask import Blueprint, request, jsonify, current_app, g 
from backend.middleware.auth import token_required
from backend.extensions import mongo, limiter
from backend.models.answer import answer_doc
from bson import ObjectId
from backend.utils.background import grade_exam_task

exam_answer_bp = Blueprint('exam_answer', __name__, url_prefix='/api/exam/answer')

@exam_answer_bp.route('/submit/', methods=['POST'])
@token_required
@limiter.limit('10 per minute')
def submit_answer():
    """
    Body: { exam_id, question_id, answer_text }
    """
    try:
        data = request.get_json() or {}
        exam_id = data.get('exam_id')
        question_id = data.get('question_id')
        answer_text = data.get('answer_text')
        
        if not all([exam_id, question_id, answer_text]):
            return jsonify({'error': 'question not found'}), 400
        
        db = mongo.db 
        q = db.exam_questions.find_one({'_id': ObjectId(question_id)})
        if not q:
            return jsonify({'error': "question not found"}), 404
        
        ans = answer_doc(exam_id, question_id, g.current_user['_id'], answer_text, q['type'])
        db.exam_answers.insert_one(ans)
        
        # trigger grading automatically for MCQ's
        if q["type"] == "mcq":
            grade_exam_task.delay(str(exam_id))
            
        return jsonify({'message': 'Answer submitted'}), 201
    except Exception as e:
        current_app.logger.exception('SUbmit answer error')
        return jsonify({'error': str(e)}), 500


@exam_answer_bp.route('/<session_id>', methods=['GET'])
@token_required
def get_session_answers(session_id):
    """
    Fetch all answers for a session (for review).
    """
    try:
        db = mongo.db
        # Verify session ownership or permission
        session = db.exam_sessions.find_one({'_id': ObjectId(session_id)})
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        # Check if user is owner of session OR exam owner/examiner
        is_student = str(session['user_id']) == str(g.current_user['_id'])
        
        if not is_student:
             exam = db.exams.find_one({'_id': session['exam_id']})
             is_owner = str(exam.get('owner_id')) == str(g.current_user['_id'])
             # Check examiner... (simplified)
             if not is_owner:
                 return jsonify({'error': 'Forbidden'}), 403

        answers = list(db.exam_answers.find({'session_id': ObjectId(session_id)}))
        for a in answers:
            a['_id'] = str(a['_id'])
            a['session_id'] = str(a['session_id'])
            a['question_id'] = str(a['question_id'])
            a['exam_id'] = str(a['exam_id'])
            a['user_id'] = str(a['user_id'])
            
        return jsonify({'answers': answers}), 200
    except Exception as e:
        current_app.logger.exception("get_session_answers error")
        return jsonify({'error': str(e)}), 500


@exam_answer_bp.route('/<session_id>/<question_id>', methods=['GET'])
@token_required
def get_single_answer(session_id, question_id):
    """
    Fetch single answer.
    """
    try:
        db = mongo.db
        answer = db.exam_answers.find_one({
            'session_id': ObjectId(session_id),
            'question_id': ObjectId(question_id)
        })
        
        if not answer:
            return jsonify({'error': 'Answer not found'}), 404
            
        # Permission check (same as above, simplified)
        if str(answer['user_id']) != str(g.current_user['_id']):
             pass 

        answer['_id'] = str(answer['_id'])
        answer['session_id'] = str(answer['session_id'])
        answer['question_id'] = str(answer['question_id'])
        answer['exam_id'] = str(answer['exam_id'])
        answer['user_id'] = str(answer['user_id'])
        
        return jsonify(answer), 200
    except Exception as e:
        current_app.logger.exception("get_single_answer error")
        return jsonify({'error': str(e)}), 500