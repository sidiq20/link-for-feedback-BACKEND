from datetime import datetime
from bson import ObjectId
import re 
import random

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

def sanitize_student_id(student_id):
    if not student_id:
        return None 
    return re.sub(r"\s+", "", student_id).upper()

def validate_question_payload(data):
    # Base checks
    if "exam_id" not in data or not is_valid_objectid(data.get("exam_id")):
        return False, "exam_id invalid"

    allowed_types = (
        "mcq", "text", "math", "boolean",
        "fill_blank", "image_label", "file_upload",
        "match", "code"
    )

    qtype = data.get("type")
    if qtype not in allowed_types:
        return False, f"Invalid or missing question type. Allowed types: {allowed_types}"

    if "prompt" not in data or not isinstance(data["prompt"], str):
        return False, "prompt is required and must be a string"

    # --- Type-specific validation ---
    # 1️⃣ Multiple Choice (Single or Multi-Select)
    if qtype == "mcq":
        opts = data.get("options") or []
        if not isinstance(opts, list) or len(opts) < 2:
            return False, "mcq must have at least 2 options"

        ans = data.get("answer_key")
        if not ans:
            return False, "mcq requires an answer_key"

        # Multi-select support: answer_key can be list
        if isinstance(ans, list):
            invalids = [a for a in ans if a not in opts]
            if invalids:
                return False, f"Invalid answer(s) {invalids} not in options"
        elif ans not in opts:
            return False, f"Invalid answer '{ans}' not in options"

    # 2️⃣ Text / Short Answer
    elif qtype == "text":
        # No strict answer_key validation since examiner grades it
        pass

    # 3️⃣ Math / Formula
    elif qtype == "math":
        ans = data.get("answer_key")
        if ans is None:
            return False, "math question must have an answer_key"

        # Numeric or expression (simple check)
        if isinstance(ans, list):
            ans = ans[0]
        if not (isinstance(ans, (int, float, str)) and str(ans).strip()):
            return False, "math answer_key must be numeric and expressions string"

    # 4️⃣ Boolean (True/False)
    elif qtype == "boolean":
        ans = data.get("answer_key")
        if ans not in [True, False, "true", "false", "True", "False"]:
            return False, "boolean question must have answer_key true/false"

    # 5️⃣ Fill in the Blank
    elif qtype == "fill_blank":
        ans = data.get("answer_key")
        if not ans:
            return False, "fill_blank must have an answer_key"
        # allow multiple acceptable answers
        if isinstance(ans, list):
            if not all(isinstance(a, str) and a.strip() for a in ans):
                return False, "all fill_blank answers must be non-empty strings"
        elif not isinstance(ans, str):
            return False, "fill_blank answer must be string or list of strings"

    # 6️⃣ Image Label / Visual
    elif qtype == "image_label":
        media = data.get("media")
        if not media or not isinstance(media, dict) or not media.get("url"):
            return False, "image_label question must include media with a valid Cloudinary URL"

        ans = data.get("answer_key")
        if not ans:
            return False, "image_label must have an answer_key (text or list)"

    # 7️⃣ File Upload
    elif qtype == "file_upload":
        allowed_ext = data.get("allowed_extensions")
        if not allowed_ext or not isinstance(allowed_ext, list):
            return False, "file_upload must include allowed_extensions list"
        max_size = data.get("max_size_mb")
        if not isinstance(max_size, (int, float)) or max_size <= 0:
            return False, "file_upload must include valid max_size_mb > 0"

    # 8️⃣ Match the Following
    elif qtype == "match":
        pairs = data.get("pairs")
        if not pairs or not isinstance(pairs, (dict, list)):
            return False, "match question must include pairs as dict or list"
        if isinstance(pairs, dict) and not pairs:
            return False, "match pairs cannot be empty"

    # 9️⃣ Code Challenge
    elif qtype == "code":
        lang = data.get("language")
        tests = data.get("test_cases")
        if not lang:
            return False, "code question must include language"
        if not tests or not isinstance(tests, list):
            return False, "code question must include test_cases list"

    # Passed all checks
    return True, None

def is_valid_student_id(student_id):
    """
    Example rule: must start with letters and contain at least one digit.
    Adjust this to your institution’s ID format.
    """
    return bool(re.match(r"^STU-\d{4}-\d{4}$", student_id))

def generate_student_id():
    year = datetime.utcnow().year
    code = random.randint(1000, 9999)
    return f"STU-{year}-{code}"