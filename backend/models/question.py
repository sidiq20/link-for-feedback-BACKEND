from datetime import datetime
from bson import ObjectId
import hashlib
import json
from backend.utils.security import hash_answer, encrypt_answer


def normalize_answer(value):
    """
    Normalize all kinds of answer types to a consistent format for hashing.
    - Strips whitespace for strings.
    - Converts booleans and numerics to canonical JSON values.
    - Sorts keys in dicts and normalizes lists recursively.
    """
    if isinstance(value, str):
        return value.strip().lower()  # normalize case for fairness
    elif isinstance(value, (int, float, bool)):
        return str(value).lower()
    elif isinstance(value, dict):
        return {k: normalize_answer(v) for k, v in sorted(value.items())}
    elif isinstance(value, list):
        return [normalize_answer(v) for v in value]
    else:
        return str(value)


def hash_answer(answer):
    """
    Hash any type of answer (text, list, dict, boolean, numeric, etc.)
    using SHA-256 after normalization and JSON serialization.
    """
    normalized = normalize_answer(answer)
    serialized = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def question_doc(
    exam_id,
    qtype,
    prompt,
    options=None,
    answer_key=None,
    points=1,
    media=None,
    shuffle_options=None,
    meta=None
):
    """
    """
    question = {
        "_id": ObjectId(),
        "exam_id": ObjectId(exam_id) if exam_id and not isinstance(exam_id, ObjectId) else exam_id,
        "type": qtype,
        "prompt": prompt,
        "points": points,
        "media": media or [],
        "meta": meta or {},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    # Only include options if explicitly provided
    if options is not None:
        question["options"] = options
        # Include shuffle_options only when options are present
        question["shuffle_options"] = shuffle_options if shuffle_options is not None else True

    if answer_key is not None:
        if isinstance(answer_key, list):
            question["answer_key_hash"] = [hash_answer(a) for a in answer_key]
            question["answer_key_encrypted"] = encrypt_answer(answer_key)
        else:
            question["answer_key_hash"] = hash_answer(answer_key)
            question["answer_key_encrypted"] = encrypt_answer(answer_key)
    else:
        question["answer_key_hash"] = None 
        question["answer_key_encrypted"] = None

    return question
