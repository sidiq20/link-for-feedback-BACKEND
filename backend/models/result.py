from datetime import datetime
from bson import ObjectId

def result_doc(
    exam_id,
    session_id,
    student_id,
    user_id,
    final_score=None,
    graded=False,
    status="in_progress",
    score=0,
    started_at=None
):
    """
    Returns a properly structured exam result document.
    """
    def to_oid(value):
        if isinstance(value, ObjectId) or value is None:
            return value
        if isinstance(value, str) and len(value) == 24:
            try:
                return ObjectId(value)
            except:
                pass
        return value

    return {
        "exam_id": to_oid(exam_id),
        "session_id": to_oid(session_id),
        "student_id": student_id,  # keep custom student codes as string
        "user_id": to_oid(user_id),
        "final_score": final_score,
        "graded": graded,
        "status": status,
        "score": score,
        "started_at": started_at or datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
