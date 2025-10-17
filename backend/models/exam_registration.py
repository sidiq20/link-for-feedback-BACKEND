from datetime import datetime
from bson import ObjectId

def registration_doc(exam_id, user_id, student_id):
    return {
        "_id": ObjectId(),
        "exam_id": ObjectId(exam_id) if exam_id and not isinstance(exam_id, ObjectId) else exam_id,
        "user_id": ObjectId(user_id) if user_id and not isinstance(user_id, ObjectId) else user_id,
        "student_id": student_id.srtip().upper(), # human readable student id
        "registered_at": datetime.utcnow(),
        "status": "registered",
    }