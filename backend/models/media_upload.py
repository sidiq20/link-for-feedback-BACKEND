from datetime import datetime
from bson import ObjectId

def media_upload_doc(owner_id, cloud_url, resource_type, public_id, exam_id=None):
    return {
        "_id": ObjectId(),
        "owner": ObjectId(owner_id),
        'cloud_url': cloud_url,
        'resourse_type': resource_type,
        'public_id': public_id,
        'exam_id': ObjectId(exam_id) if exam_id else None,
        'created_at': datetime.utcnow()
    }