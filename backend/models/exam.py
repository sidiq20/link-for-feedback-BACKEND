from datetime import datetime
from bson import ObjectId

def exam_doc(title, description, start_time, end_time, duration_seconds, owner_id, code, settings=None):
    return {
        "_id": ObjectId(),
        "title": title,
        "description": description,
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": duration_seconds,
        "owner_id": ObjectId(owner_id) if owner_id and not isinstance(owner_id, ObjectId) else owner_id,
        "code": code,
        "status": "draft",
        "settings": settings or {
            "proctoring": False,
            "strict_mode": True,
            "randomize_question": True,
            "max_tab_switches": 3,
            "auto_submit_on_violation": False
        },
        "question_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }