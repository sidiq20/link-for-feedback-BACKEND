from datetime import datetime
from bson import ObjectId
from backend.models.question import hash_answer, encrypt_answer

def answer_doc(exam_id, question_id, user_id, answer_text, question_type):
    
    answer_hash = hash_answer(answer_text)
    encrypt_answer = None 
    if question_type != "mcq":
        encrypt_answer = encrypt_answer(answer_text)
    return {
        '_id': ObjectId(),
        'exam_id': ObjectId(exam_id),
        'question_id': ObjectId(question_id),
        'user_id': ObjectId(user_id),
        'answer_hash': answer_hash,
        'answer_encrypted': encrypt_answer,
        'answer_text': None if question_type == "mcq" else None,
        'submitted_at': datetime.utcnow()
    }
    