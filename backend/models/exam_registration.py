from datetime import datetime
from bson import ObjectId

def registration_doc(exam_id, user_id, student_id):
    return {
        "_id": ObjectId(),
        "exam_id": ObjectId(exam_id) if not isinstance(exam_id, ObjectId) else exam_id,
        "user_id": ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id,
        "student_id": student_id.strip().upper(),
        "registered_at": datetime.utcnow(),
        "status": "registered",
    }
