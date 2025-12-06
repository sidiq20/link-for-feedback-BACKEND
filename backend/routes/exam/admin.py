from flask import Blueprint, request, jsonify, current_app, g
from backend.middleware.auth import token_required
from bson import ObjectId
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def require_admin():
    if g.current_user.get('role') != 'admin':
        return False
    return True

@admin_bp.route('/users', methods=['GET'])
@token_required
def list_users():
    if not require_admin(): return jsonify({'error': 'Forbidden'}), 403
    try:
        db = current_app.mongo.db
        users = list(db.users.find({}, {'password': 0}).limit(100))
        for u in users:
            u['_id'] = str(u['_id'])
        return jsonify({'users': users}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/exams', methods=['GET'])
@token_required
def list_exams():
    if not require_admin(): return jsonify({'error': 'Forbidden'}), 403
    try:
        db = current_app.mongo.db
        exams = list(db.exams.find({}).limit(100))
        for e in exams:
            e['_id'] = str(e['_id'])
            e['owner_id'] = str(e['owner_id'])
        return jsonify({'exams': exams}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/logs', methods=['GET'])
@token_required
def list_logs():
    if not require_admin(): return jsonify({'error': 'Forbidden'}), 403
    try:
        db = current_app.mongo.db
        # Assuming a general logs collection or proctor logs
        logs = list(db.proctor_logs.find({}).sort('timestamp', -1).limit(100))
        for l in logs:
            l['_id'] = str(l['_id'])
            l['session_id'] = str(l['session_id'])
        return jsonify({'logs': logs}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/exams/disable/<exam_id>', methods=['POST'])
@token_required
def disable_exam(exam_id):
    if not require_admin(): return jsonify({'error': 'Forbidden'}), 403
    try:
        db = current_app.mongo.db
        db.exams.update_one({'_id': ObjectId(exam_id)}, {'$set': {'status': 'disabled', 'updated_at': datetime.utcnow()}})
        return jsonify({'message': 'Exam disabled'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/config/update', methods=['POST'])
@token_required
def update_config():
    if not require_admin(): return jsonify({'error': 'Forbidden'}), 403
    try:
        data = request.get_json() or {}
        # Mock config update
        return jsonify({'message': 'Config updated', 'config': data}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
