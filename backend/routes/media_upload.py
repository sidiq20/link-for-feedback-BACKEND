from flask import Blueprint, request, jsonify, current_app, g 
from backend.middleware.auth import token_required
from backend.models.media_upload import media_upload_doc
from backend.extensions import mongo, limiter 
from backend.utils.cloudinary_helper import upload_media

media_upload_bp = Blueprint('media_upload', __name__, url_prefix='/api/exam_media')

@media_upload_bp.route('/upload', methods=['POST'])
@token_required
@limiter.limit('5 per minute')
def upload_exam_media():
    """
    Multipart Form: { file: <image>, exam_id (optional) }
    """
    try:
        file = request.files.get('file')
        exam_id = request.form.get('exam_id')
        
        if not file:
            return jsonify({'error': 'File required'}), 400 
        
        url, public_id, resource_type = upload_media(file)
        doc = media_upload_bp(
            ownner_id=g.current_user['_id'],
            cloud_url=url,
            resource_type=resource_type,
            public=public_id,
            exam_id=exam_id
        )
        mongo.db.exam_media.insert_one(doc)
        
        return jsonify({"message": "Uploaded", "url": url, "public_id": public_id}), 201 
    except Exception as e:
        current_app.logger.exception("Upload media error")
        return jsonify({"error": str(e)}), 500