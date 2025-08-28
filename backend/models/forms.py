from datetime import datetime
from bson import ObjectId
from flask import current_app
from backend.utils.validation import to_objectid
from backend.models.response import RESPONSE

class FORM:
    COLLECTION = "forms"
    
    @staticmethod
    def get_collection():
        return current_app.mongo.db[FORM.COLLECTION]
    
    @staticmethod
    def validate_questions(questions):
        if not isinstance(questions, list) or len(questions) == 0:
            return False, "Questions muct be a non-empty list"
        
        allowed_types = ["text", "radio", "checkbox", "poll", "date", "number"]
        
        for idx, q in enumerate(questions):
            
            q_text = q.get("question") or q.get("text")
            if not isinstance(q_text, str) or not q_text.strip():
                return False, f"Question {idx+1} non-empy 'question' field"
            
            q_type = q.get("type")
            if q_type not in allowed_types:
                return False, f"Question {idx+1} has invalid type '{q_type}'"
            
            options = q.get("options", [])
            
            
            if q_type in ["radio", "checkbox", "poll"]:
                if not isinstance(options, list) or len(options) < 2:
                    return False, f"Question {idx+1} must have at least 2 options"
                
                if not all(isinstance(opt, str) and opt.strip() for opt in options):
                    return False, f"Question {idx+1} has invalid options"
            elif q_type == "text" and "options" in q:
                return False, f"Question {idx+1} (text) should not have options"
            
            if q_type == "number":
                min_val = q.get("min")
                max_val = q.get("max")
                if min_val is not None and not isinstance(min_val, (int, float)):
                    return False, f"Question {idx+1} min must be a number" 
                if max_val is not None and not isinstance(max_val, (min, float)):
                    return False, f"Question {idx+1} max must be a number" 
                if min_val is not None and max_val is not None and min_val > max_val:
                    return False, f"Question {idx+1} min cannot be greater than max"
                
            if q_type == "date":
                min_date = q.get("min")
                max_date = q.get("max")
                if min_date and not isinstance(min_date, str):
                    return False, f"Question {idx+1} min must be a date string (YYYY-MM-DD)"
                if max_date and not isinstance(max_date, str):
                    return False, f"Question {idx+1} max must be a date string (YYYY-MM-DD)"
                # optional: parse to validate format
                # from datetime import datetime
                # try: datetime.strptime(min_date, "%Y-%m-%d") if min_date else None
                # except: return False, f"Question {idx+1} has invalid min date format"
                
                
                
            
            if "required" in q and not isinstance(q["required"], bool):
                return False, f"Question {idx+1} 'required' must be a boolean"
            
        return True, "Valid"
    
    @staticmethod
    def validate_responses(question, responses):
        if not isinstance(responses, dict):
            return False, "Response must be a dictionary" 
        
        for idx, q in enumerate(question):
            q_type = q["type"]
            required = q.get("required", False)
            answer = responses.get(str(idx+1))
            
            if required and (answer is None or (isinstance(answer, str) and not answer.strip())):
                return False, f"Question {idx+1} is required"
            
            if answer is None:
                continue
            
            if q_type == "text":
                if not isinstance(answer, str):
                    return False, f"Question {idx+1} must be a text answer"
                
            elif q_type == "radio":
                if answer not in q["options"]:
                    return False, f"Question {idx+1} answer must be one of {q['options']}"
                
            elif q_type == "checkbox":
                if not isinstance(answer, list):
                    return False, f"Question {idx+1} must be a list of answers" 
                invalid_opts = [opt for opt in answer if opt not in q["options"]]
                if invalid_opts:
                    return False, f"Question {idx+1} has invalid options {invalid_opts}"
                
            elif q_type == "poll":
                if answer not in [opt["label"] for opt in q["options"]]:
                    return False, f"Answer for qestion {idx+1}  must be one of {q['options']}"
                
            elif q_type == "number":
                if not isinstance(answer, (int, float)):
                    return False, f"Question {idx+1} must be a number" 
                if q.get("min") is not None and answer < q["min"]:
                    return False, f"Question {idx+1} must be >= {q['min']}"
                if q.get("max") is not None and answer > q["max"]:
                    return False, f"Question {idx+1} must be <= {q['max']}"
                
            elif q_type == "date":
                if not isinstance(answer, str):
                    return False, f"Question {idx+1} must be a date string (YYYY-MM-DD)"
                # optional: validate format and range
                # from datetime import datetime
                # try:
                #     dt = datetime.strptime(answer, "%Y-%m-%d")
                # except:
                #     return False, f"Question {idx+1} has invalid date format"
                # if q.get("min"): min_dt = datetime.strptime(q["min"], "%Y-%m-%d"); 
                # if dt < min_dt: return False, ...
    
        return True, "Valid"
    
    @staticmethod
    def vote(form_id, question_index, option_label):
        form = FORM.get_by_id(form_id)
        if not form:
            return False, "form not found"
        
        try:
            question = form["questions"][question_index]
        except IndexError:
            return False, "Invalid question index"
        
        if question["type"] != "poll":
            return False, f"This question is type '{question['type']}', only 'poll' supports voting"

        updated = False 
        for idx, opt in enumerate(question["options"]):
            # Case 1: option stored as string
            if isinstance(opt, str) and opt == option_label:
                # Convert string to dict with first vote
                question["options"][idx] = {"label": opt, "votes": 1}
                updated = True
                break
            # Case 2: option already stored as dict
            elif isinstance(opt, dict) and opt.get("label") == option_label:
                question["options"][idx]["votes"] = question["options"][idx].get("votes", 0) + 1
                updated = True
                break
        
        if not updated:
            return False, "Option not found" 
        
        FORM.get_collection().update_one(
            {"_id": form["_id"]},
            {
                "$set": {
                "questions": form["questions"],
                "updated_at": datetime.utcnow()
                }
            }
        )
        return True, "vote counted"

    
    @staticmethod
    def create(user_id, title, description, questions):
        is_valid, msg = FORM.validate_questions(questions)
        if not is_valid:
            raise ValueError(msg)
        
        doc = {
            "user_id": to_objectid(user_id),
            "title": title,
            "description": description,
            "questions": [
                {
                    **q,
                    "question": q.get("question") or q.get("text")
                }
                for q in questions
            ],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = FORM.get_collection().insert_one(doc)
        return str(result.inserted_id)
    
    @staticmethod
    def get_by_id(form_id):
        return FORM.get_collection().find_one({"_id": ObjectId(form_id)})
    
    @staticmethod
    def get_by_user(user_id):
        return list(FORM.get_collection().find({"user_id": to_objectid(user_id)}))
    
    @staticmethod
    def update(form_id, update_data):
        update_data["updated_at"] = datetime.utcnow()
        return FORM.get_collection().update_one(
            {"_id": ObjectId(form_id)},
            {"$set": update_data}
        )
        
    @staticmethod
    def delete(form_id):
        return FORM.get_collection().delete_one({"_id": ObjectId(form_id)})
    
    
    @staticmethod
    def get_results(form_id):
        form = FORM.get_by_id(form_id)
        if not form:
            return None, "Form not found"

        results = []

        for q_index, question in enumerate(form["questions"]):
            if question["type"] == "poll":
                # Poll results: already stored as counts in form
                poll_results = []
                for opt in question["options"]:
                    # option is dict {"label": ..., "votes": ...}
                    poll_results.append({
                        "label": opt["label"],
                        "votes": opt.get("votes", 0)
                    })
                results.append({
                    "type": "poll",
                    "question": question["question"],
                    "results": poll_results
                })

            elif question["type"] == "radio":
                # Radio results: aggregate responses from RESPONSE collection
                pipeline = [
                    {"$match": {"form_id": form_id, "question_index": q_index}},
                    {"$group": {"_id": "$answer", "count": {"$sum": 1}}},
                    {"$project": {"label": "$_id", "votes": "$count", "_id": 0}}
                ]
                radio_results = list(RESPONSE.get_collection().aggregate(pipeline))
                results.append({
                    "type": "radio",
                    "question": question["question"],
                    "results": radio_results
                })

            elif question["type"] == "text":
                # Text answers: return as a list of user submissions
                text_answers = RESPONSE.get_collection().find(
                    {"form_id": form_id, "question_index": q_index},
                    {"_id": 0, "answer": 1}
                )
                results.append({
                    "type": "text",
                    "question": question["question"],
                    "answers": [doc["answer"] for doc in text_answers]
                })

        return results, None
