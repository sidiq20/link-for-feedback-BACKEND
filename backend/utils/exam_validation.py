from datetime import datetime
from bson import ObjectId
import re 

def is_valid_objectid(oid):
    try: 
        ObjectId(str(oid))
        return True 
    except Exception:
        return False 
    
def validate_exam_payload(data):
    required = ["title", "duration_seconds", "code"]
    for k in required:
        if k not in data:
            return False, f"{k} is required"
        
    if "start_time" in data:
        try:
            if isinstance(data["start_time"], str):
                datetime.fromisoformat(data["start_time"])
        except Exception:
            return False, "start_time must be ISO format"
    return True, None

def validate_question_payload(data):
    if "exam_id" not in data or not is_valid_objectid(data.get("exam_id")):
        return False, "exam_id invalid"
    if "type" not in data or data["typee"] not in ("mcq", "text", "file_upload", "image_label"):
        return False, "invalid or missing question type"
    if "prompt" not in data or not isinstance(data["prompt"], str):
        return False, "prompt is required"
    if data["type"] == "mcq":
        opts = data.get("options") or []
        if not isinstance(opts, list) or len(opts) < 2:
            return False, "mcq must have at least 2 questions"
    return True, None

def sanitize_student_id(student_id):
    if not student_id:
        return None 
    return re.sub(r"\s+", "", student_id).upper()