from datetime import datetime
from bson import ObjectId

def result_doc(exam_id, session_id, student_id, final_score=None, graded=False, status="in_progress"):
    return {
        "_id": ObjectId(),
        "exam_id": ObjectId(exam_id) if exam_id and not isinstance(exam_id, ObjectId) else exam_id,
        "session_id": ObjectId(session_id) if session_id and not isinstance(session_id, ObjectId) else session_id,
        "student_id": ObjectId(student_id) if student_id and not isinstance(student_id, ObjectId) else student_id,
        "final_score": final_score,
        "graded": graded,
        "status": status,
        "created_at": datetime.utcnow(),
        "created_at": datetime.utcnow()
    }