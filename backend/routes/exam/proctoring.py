from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from bson import ObjectId
from datetime import datetime

proctoring_bp = Blueprint('proctoring', __name__, url_prefix='/api/proctoring')

@proctoring_bp.route('/<session_id>/logs', methods=['GET'])
@token_required
def get_proctor_logs(session_id):
    """
    Get all proctor logs for a session.
    """
    try:
        db = current_app.mongo.db
        session = db.exam_sessions.find_one({'_id': ObjectId(session_id)})
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        # Permission check: owner or examiner
        exam = db.exams.find_one({'_id': session['exam_id']})
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        logs = list(db.proctor_logs.find({'session_id': ObjectId(session_id)}).sort('timestamp', 1))
        for log in logs:
            log['_id'] = str(log['_id'])
            log['session_id'] = str(log['session_id'])
            
        return jsonify({'logs': logs}), 200
    except Exception as e:
        current_app.logger.exception("get_proctor_logs error")
        return jsonify({'error': str(e)}), 500


@proctoring_bp.route('/<exam_id>/students/live', methods=['GET'])
@token_required
def get_live_students(exam_id):
    """
    Live monitored sessions.
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
            
        # Permission check
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        sessions = list(db.exam_sessions.find({
            'exam_id': ObjectId(exam_id),
            'status': 'in_progress'
        }))
        
        live_data = []
        for s in sessions:
            user = db.users.find_one({'_id': s['user_id']})
            live_data.append({
                'session_id': str(s['_id']),
                'student_id': str(s['user_id']),
                'name': user.get('name') if user else 'Unknown',
                'started_at': s.get('started_at'),
                'violation_count': s.get('violation_count', 0),
                'last_heartbeat': s.get('updated_at') # Assuming updated_at is touched on heartbeat
            })
            
        return jsonify({'live_sessions': live_data}), 200
    except Exception as e:
        current_app.logger.exception("get_live_students error")
        return jsonify({'error': str(e)}), 500


@proctoring_bp.route('/<session_id>/flag', methods=['POST'])
@token_required
def manual_flag_incident(session_id):
    """
    Examiner manually flags incident.
    """
    try:
        db = current_app.mongo.db
        data = request.get_json() or {}
        reason = data.get('reason', 'Manual flag by proctor')
        
        session = db.exam_sessions.find_one({'_id': ObjectId(session_id)})
        if not session:
            return jsonify({'error': 'Session not found'}), 404
            
        # Permission check
        exam = db.exams.find_one({'_id': session['exam_id']})
        if str(g.current_user['_id']) not in [str(exam['owner_id'])] + [str(x) for x in exam.get('invited_examiners', [])]:
            return jsonify({'error': 'Unauthorized'}), 403

        # Log incident
        incident = {
            'session_id': ObjectId(session_id),
            'event_type': 'manual_flag',
            'details': {'reason': reason, 'flagged_by': ObjectId(g.current_user['_id'])},
            'timestamp': datetime.utcnow()
        }
        db.proctor_logs.insert_one(incident)
        
        # Update session violation count
        db.exam_sessions.update_one(
            {'_id': ObjectId(session_id)},
            {'$inc': {'violation_count': 1}, '$set': {'updated_at': datetime.utcnow()}}
        )
        
        return jsonify({'message': 'Session flagged'}), 200
    except Exception as e:
        current_app.logger.exception("manual_flag_incident error")
        return jsonify({'error': str(e)}), 500
