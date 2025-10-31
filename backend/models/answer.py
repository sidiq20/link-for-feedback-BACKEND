from datetime import datetime
from bson import ObjectId
from backend.models.question import hash_answer


def answer_doc(exam_id, question_id, user_id, answer_text, question_type):
    return {
        '_id': ObjectId(),
        'exam_id': ObjectId(exam_id),
        'question_id': ObjectId(question_id),
        'user_id': ObjectId(user_id),
        'answer_hash': hash_answer(answer_text),
        'answer_text': answer_text if question_type != "mcq" else None,
        'submitted_at': datetime.utcnow()
    }
    
def verify_answer(submitted_answer, stored_answer_key):
    pass