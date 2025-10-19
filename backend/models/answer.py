from datetime import datetime
from bson import ObjectId
from backend.utils.hashing import hash_answer_key


def answer_doc(exam_id, question_id, user_id, answer_text, question_type):
    return {
        '_id': ObjectId(),
        'exam_id': ObjectId(exam_id),
        'question_id': ObjectId(question_id),
        'user_id': ObjectId(user_id),
        'answer_hash': hash_answer_key(answer_text),
        'answer_text': answer_text if question_type != "mcq" else None,
        'submitted_at': datetime.utcnow()
    }