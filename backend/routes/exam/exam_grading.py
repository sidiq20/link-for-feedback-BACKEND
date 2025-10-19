from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from backend.utils.background import grade_exam_task
from backend.extensions import mongo, limiter
from bson import ObjectId

exam_grading_bp = Blueprint('exam_grading', __name__, url_prefix='/api/exam_grade')

@exam_grading_bp.route('/trigger/<exam_id>', methods=['POST'])
@token_required
@limiter.limit('3 per minute')
def trigger_grading(exam_id):
    """Manually trigger background grading. """
    try:
        db = mongo.db 
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unautorized'}), 403
        
        grade_exam_task.delay(str(exam_id))
        return jsonify({'message': 'Grading started'}), 200
    except Exception as e:
        current_app.logger.exception('Trigger grading error')
        return jsonify({'error': str(e)}), 500
    
@exam_grading_bp.route('/manual/<exam_id>/<student_id>', methods=['POST'])
@token_required
@limiter.limit('5 per minute')
def manual_grade(exam_id, student_id):
    """
    Body: [{ question_id, score, comment? }, ... ]
    """
    try:
        db = mongo.db 
        data = request.get_json() or []
        
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403
        
        total_score = 0 
        for entry in data:
            total_score += entry.get('score', 0)
            db.manual_grades.insert_one({
                'exam_id': ObjectId(exam_id),
                'student_id': student_id,
                'question_id': ObjectId(entry['question_id']),
                'score': entry.get('scoore', 0),
                'comment': entry.get('comment', ''),
                'graded_by': g.current_user['_id']
            })
            
        db.exam_results.update_one(
            {'exam_id': ObjectId(exam_id), 'user_id': ObjectId(student_id)},
            {'$set': {'total_score': total_score, 'graded': True, 'graded_at': current_app.now()}},
            upsert=True
        )
        
        return jsonify({'message': 'Manual grading saved', 'total_score': total_score}), 200
    except Exception as e:
        current_app.logger.exception('Manual grading error')
        return jsonify({'error': str(e)}), 500