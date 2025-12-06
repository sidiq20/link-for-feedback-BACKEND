from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from bson import ObjectId
from datetime import datetime

exam_portal_bp = Blueprint('exam_portal', __name__, url_prefix='/api/exam/portal/')

@exam_portal_bp.route('/dashboard', methods=['GET'])
@token_required
def portal_dashboard():
    """
    Returns summary: registred exams, recent results, upcoming exams
    """
    try:
        db = current_app.mongo.db
        user_id = ObjectId(g.current_user['_id'])
        
        regs = list(db.exam_registration.find({'user_id': user_id}))
        exam_ids = [r['exam_id'] for r in regs if 'exam_id' in r]
        
        # get all exam for in one go to reduce queries
        exams = {e['_id']: e for e in db.exams.find({'_id': {'$in': exam_ids}})}
        
        registered = []
        for r in regs:
            exam = exams.get(r['exam_id'])
            registered.append({
                'exam_id': str(r['exam_id']),
                'title': exam.get('title') if exam else None,
                'student_id': r.get('student_id'),
                'registered_at': r.get('registered_at')
            })
            
        results = list(
            db.exam_results
                .find({'student_id': str(user_id)})
                .sort('created_at', -1)
                .limit(10)
        )
        
        recent = []
        for res in results:
            exam = exams.get(res['exam_id']) or db.exams.find_one({'_id': res['exam_id']})
            recent.append({
                'exam_title': exam.get('title') if exam else None,
                'final_score': res.get('final_score'),
                'status': res.get('status'),
                'graded': res.get('graded')
            })
            
        now = datetime.utcnow()
        upcoming = list(
            db.exams.find(
                {'status': 'published', 'start_time': {'$gt': now}}
            ).limit(10)
        )
        
        return jsonify({
            'registered': registered,
            'recent_results': recent,
            'upcoming': [
                {
                    'exam_id': str(e['_id']),
                    'title': e.get('title'),
                    'start_time': e.get('start_time')
                }
                for e in upcoming
            ]
        }), 200
    
    except Exception as e:
        current_app.logger.exception('Portal dahsboard error')
        return jsonify({'error': 'Failed to fecth dahsboards'})


@exam_portal_bp.route('/proctor_dashboard/<exam_id>', methods=['GET'])
@token_required
def proctor_dashboard(exam_id):
    """
    Live proctor view.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
            
        # Permission check: owner or examiner
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        # Fetch active sessions
        sessions = list(db.exam_sessions.find({
            'exam_id': ObjectId(exam_id),
            'status': 'in_progress'
        }))
        
        active_students = []
        for s in sessions:
             user = db.users.find_one({'_id': s['user_id']})
             active_students.append({
                 'session_id': str(s['_id']),
                 'student_name': user.get('name') if user else 'Unknown',
                 'started_at': s.get('started_at'),
                 'violation_count': s.get('violation_count', 0)
             })
             
        return jsonify({
            'exam_title': exam.get('title'),
            'active_sessions': active_students,
            'total_active': len(active_students)
        }), 200
    except Exception as e:
        current_app.logger.exception("proctor_dashboard error")
        return jsonify({'error': str(e)}), 500