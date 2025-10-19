from flask import Blueprint, request, jsonify, current_app, g 
from backend.middleware.auth import token_required
from backend.extensions import mongo, limiter
from bson import ObjectId

exam_invite_bp = Blueprint('exam_invite', __name__, url_prefix='/api/exam/invite/')

@exam_invite_bp.route('<exam_id>', methods=['POST'])
@token_required
@limiter.limit('3 per minute')
def invite_examiner(exam_id):
    """
    Body: {examiner_ids: [str] }
    """
    try:
        data = request.get_json() or {}
        examiner_ids = data.get('examiner_ids', [])
        
        if not examiner_ids:
            return jsonify({'error': 'examiner_ids required'}), 400
        
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404
        
        new_examiners = [ObjectId(e) for e in examiner_ids if ObjectId.is_valid(e)]
        db.exams.update_one(
            {'_id': exam['_id']},
            {'$addToSet': {'invited_examiners': {'$each': new_examiners}}}
        )
        
        return jsonify({'message': 'Examiners invited'}), 200
    except Exception as e:
        current_app.logger.exception('Invite examiner error')
        return jsonify({'error': str(e)}), 500