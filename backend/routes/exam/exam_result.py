from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from bson import ObjectId
from backend.extensions import limiter

exam_result_bp = Blueprint('exam_result', __name__, url_prefix="/api/exam/results/")

@exam_result_bp.route("/<exam_id>/all/", methods=['GET'])
@limiter.limit('5 per minute')
@token_required
def exam_results_all(exam_id):
    # only exam owner should access
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 400
        if str(exam.get('owner_id')) != str(g.current_user['_id']):
            return jsonify({'error': 'Forbidden'}), 403
        
        results = list(db.exam_results.find({'exam_id': exam['_id']}))
        out = []
        for r in results:
            user = db.users.find_one({'_id': ObjectId(r["student_id"])})
            out.append({
                'result_id': str(r['_id']),
                'session_id': str(r['session_id']),
                'student': {'id': str(user['_id']), 'name': user.get('name')},
                'email': user.get('email') if user else None,
                'final_score': r.get('final_score'),
                'graded': r.get('graded'),
                'status': r.get('status')
            })
        return jsonify({'results': out}), 200
    except Exception as e:
        current_app.logger.exception('Get exam results error')
        return jsonify({'error': 'Failed to fetch results'}), 500

@exam_result_bp.route("/student/<student_id>/list", methods=['GET'])
@token_required
def student_results(student_id):
    # student can access thier own results
    try:
        db = current_app.mongo.db
        # ensures student_id matches current user
        if str(g.current_user['_id']) != student_id:
            # later for admins? for now only owner
            # if student wants to view by student_id mapping, fine registraion mapping
            pass
         
        # fetch registration for this year 
        regs = list(db.exam_registration.find({'user_id': ObjectId(g.current_user['_id'])}))
        exam_ids = [r['exam_id'] for r in regs]
        results = list(db.exam_results.find({'exam_id': {'$in': exam_ids}, 'student_id': ObjectId(g.current_user['_id'])}))
        out = []
        for r in results:
            exam = db.exams.find_one({'_id': r['exam_id']})
            out.append({
                'exam_id': str(r['exam_id']),
                'exam_title': exam.get('title') if exam else None,
                'final_score': r.get('final_score'),
                'status': r.get('status'),
                'graded': r.get('graded')
            })
        return jsonify({'results': out}), 200
    except Exception as e:
        current_app.logger.exception('Get student results error')
        return jsonify({'error': 'Failed to fecth student results'}), 500