from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from backend.utils.background import grade_exam_task
from backend.extensions import mongo, limiter
from bson import ObjectId
from datetime import datetime

exam_grading_bp = Blueprint('exam_grading', __name__, url_prefix='/api/exam_grading')

@exam_grading_bp.route('/trigger/<exam_id>', methods=['POST'])
@token_required
@limiter.limit('10 per minute')
def trigger_grading(exam_id):
    """Manually trigger background grading. """
    try:
        db = current_app.mongo.db 
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403
        
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
        db = current_app.mongo.db 
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
                'score': entry.get('score', 0),
                'comment': entry.get('comment', ''),
                'graded_by': g.current_user['_id']
            })
            
        db.exam_results.update_one(
            {'exam_id': ObjectId(exam_id), 'user_id': ObjectId(student_id)},
            {'$set': {'total_score': total_score, 'graded': True, 'graded_at': datetime.utcnow()}},
            upsert=True
        )
        
        return jsonify({'message': 'Manual grading saved', 'total_score': total_score}), 200
    except Exception as e:
        current_app.logger.exception('Manual grading error')
        return jsonify({'error': str(e)}), 500
    

@exam_grading_bp.route('/<exam_id>/results', methods=['GET'])
@token_required
def get_grading_results(exam_id):
    try:
        db = current_app.mongo.db

        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404

        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        results = list(db.exam_results.find({'exam_id': ObjectId(exam_id)}))
        for result in results:
            result['_id'] = str(result['_id'])
            result['exam_id'] = str(result['exam_id'])
            result['user_id'] = str(result['user_id'])

        return jsonify(results), 200
    except Exception as e:
        current_app.logger.exception('Get grading results error')
        return jsonify({'error': str(e)}), 500


@exam_grading_bp.route('/<exam_id>/results/<student_id>', methods=['GET'])
@token_required
def get_student_grading_results(exam_id, student_id):
    try:
        db = current_app.mongo.db

        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404

        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        result = db.exam_results.find_one({'exam_id': ObjectId(exam_id), 'user_id': ObjectId(student_id)})
        if not result:
            return jsonify({'error': 'Result not found'}), 404

        result['_id'] = str(result['_id'])
        result['exam_id'] = str(result['exam_id'])
        result['user_id'] = str(result['user_id'])

        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception('Get student grading results error')
        return jsonify({'error': str(e)}), 500


@exam_grading_bp.route('/<exam_id>/results/<student_id>', methods=['PUT', 'PATCH'])
@token_required
def update_student_grading_results(exam_id, student_id):
    try:
        db = current_app.mongo.db

        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404

        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = db.exam_results.find_one({'exam_id': ObjectId(exam_id), 'user_id': ObjectId(student_id)})
        if not result:
            return jsonify({'error': 'Result not found'}), 404

        # Update the result with the new data
        update_data = {}
        if 'score' in data:
            update_data['score'] = data['score']
        if 'feedback' in data:
            update_data['feedback'] = data['feedback']
        if 'graded_by' in data:
            update_data['graded_by'] = data['graded_by']
        if 'graded_at' in data:
            update_data['graded_at'] = data['graded_at']
        if 'status' in data:
            update_data['status'] = data['status']

        if update_data:
            db.exam_results.update_one(
                {'_id': result['_id']},
                {'$set': update_data}
            )

        updated_result = db.exam_results.find_one({'_id': result['_id']})
        updated_result['_id'] = str(updated_result['_id'])
        updated_result['exam_id'] = str(updated_result['exam_id'])
        updated_result['user_id'] = str(updated_result['user_id'])

        return jsonify(updated_result), 200
    except Exception as e:
        current_app.logger.exception('Update student grading results error')
        return jsonify({'error': str(e)}), 500


@exam_grading_bp.route('/<exam_id>/analytics', methods=['GET'])
@token_required
def get_exam_analytics(exam_id):
    """
    Stats, histograms, difficulty.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
        
        # Permission check
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        pipeline = [
            {'$match': {'exam_id': ObjectId(exam_id), 'status': 'submitted'}},
            {'$group': {
                '_id': None,
                'avg_score': {'$avg': '$final_score'},
                'min_score': {'$min': '$final_score'},
                'max_score': {'$max': '$final_score'},
                'count': {'$sum': 1}
            }}
        ]
        stats = list(db.exam_results.aggregate(pipeline))
        stats = stats[0] if stats else {}
        if '_id' in stats: del stats['_id']
        
        return jsonify({'analytics': stats}), 200
    except Exception as e:
        current_app.logger.exception("get_exam_analytics error")
        return jsonify({'error': str(e)}), 500


@exam_grading_bp.route('/<exam_id>/item_analysis', methods=['GET'])
@token_required
def get_item_analysis(exam_id):
    """
    Per-question performance.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
            
        # Permission check
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        # Aggregate answers to calculate difficulty (avg score per question)
        pipeline = [
            {'$match': {'exam_id': ObjectId(exam_id), 'status': 'submitted'}},
            {'$unwind': '$detailed'},
            {'$group': {
                '_id': '$detailed.question_id',
                'avg_score': {'$avg': '$detailed.awarded'},
                'attempts': {'$sum': 1}
            }}
        ]
        analysis = list(db.exam_results.aggregate(pipeline))
        
        return jsonify({'item_analysis': analysis}), 200
    except Exception as e:
        current_app.logger.exception("get_item_analysis error")
        return jsonify({'error': str(e)}), 500