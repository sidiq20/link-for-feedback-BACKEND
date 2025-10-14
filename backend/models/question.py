from datetime import datetime
from bson import ObjectId

def question_doc(exam_id, qtype, prompt, options=None, answer_key=None, points=1, media=None, shuffle_options=True):
    return {
        "_id": ObjectId(),
        "exam_id": ObjectId(exam_id) if exam_id and not isinstance(exam_id, ObjectId)else exam_id,
        "type": qtype,
        "prompt": prompt,
        "options": options or [],
        "answer_key": answer_key,
        "points": points,
        "media": media or [],
        "shuffle_options": shuffle_options,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }