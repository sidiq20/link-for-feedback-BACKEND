from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from bson import ObjectId

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
        regs = list(db.exam_registraion.find({'user_id': user_id}))
        registered = []
        exam_ids = [r['exam_ids'] for r in regs]
        for r in regs:
            exam = db.exams.find_one({'_id': r['exam_id']})
            registered.append({
                'exam_id': str(r['exam_id']),
                'title': exam.get('title') if exam else None,
                'student_id': r.get('student_id'),
                'registered_at': r.get('registered_at')
            })
            
        results = list(db.exam_results.find({'student_id': user_id})).sort('created_at', 1).limit(10)
        recent = []
        for res in results:
            exam = db.exams.find_one({'_id': res['exam_id']})
            recent.append({
                'exam_title': exam.get('title') if exam else None,
                'final_score': res.get('final_score'),
                'status': res.get('status'),
                'graded': res.get('graded')
            })
        
        # upcoming exams (published and starrt_time > now)
        import datetime
        now = datetime.datetime.utcnow()
        upcoming = list(db.exams.find({'status': 'published', 'start_time': {'$gt': now}}).limit(10))
        
        return jsonify({
            'registered': registered,
            'recent_results': recent,
            'upcoming': [{
                'exam_id': str(e['_id']),
                'tiltle': e['title'],
                'start_time': e.get('start_time')} for e in upcoming
        ]})
        
    except Exception as e:
        current_app.logger.exception('Portal dahsboard error')
        return jsonify({'error': 'Failed to fetch dashboard'}), 500