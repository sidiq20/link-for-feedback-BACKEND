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