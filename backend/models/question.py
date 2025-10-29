from datetime import datetime
from bson import ObjectId
import hashlib

def hash_answer(answer):
    if not answer:
        return None
    if isinstance(answer, list):
        answer = "|".join(map(str, answer))
    return hashlib.sha256(answer.encode()).hexdigest()

def question_doc(exam_id, qtype, prompt, options=None, answer_key=None, points=1, media=None, shuffle_options=True, meta=None):
    # qtype: mcp, text,math, boolean, essay, fileupload, image_label
    # media: uploaded CLoudinary url or metadata dict
    
    question =  {
        "_id": ObjectId(),
        "exam_id": ObjectId(exam_id) if exam_id and not isinstance(exam_id, ObjectId)else exam_id,
        "type": qtype,
        "prompt": prompt,
        "options": options or [],
        "points": points,
        "media": media or [],
        "shuffle_options": shuffle_options,
        "meta": meta or {},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    # only MCP or boolean question have answer keys
    if qtype in ("mcq", "boolean"):
        question["answer_key"] = hash_answer(answer_key)
    else:
        question["answer_key"] = None
        
    return question 