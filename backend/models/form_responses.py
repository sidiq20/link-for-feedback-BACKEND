from datetime import datetime
from bson import ObjectId
from flask import current_app

class FORM_RESPONSE:
    COLLECTION = "form_response" 
    
    @staticmethod
    def get_collection():
        return current_app.mongo.db[FORM_RESPONSE.COLLECTION]
    
    @staticmethod
    def submit(form_id, answers, responder_ip=None):
        doc = {
            "form_id": ObjectId(form_id),
            "answers": answers,
            "responder_ip": responder_ip,
            "submitted_at": datetime.utcnow()
        }
        result = FORM_RESPONSE.get_collection().insert_one(doc)
        return str(result.inserted_id)
       
    @staticmethod
    def get_by_form(form_id):
        return list(FORM_RESPONSE.get_collection().find({"form_id": ObjectId(form_id)}))
    
    @staticmethod
    def get_poll_results(form_id):
        responses = FORM_RESPONSE.get_by_form(form_id)
        poll_results = {}
        
        for response in responses:
            for ans in response["answers"]:
                q = ans["questions"]
                a = ans["answer"]
                
                if isinstance(a, list):
                    for option in a:
                        poll_results.setdefault(q, {}).setdefault(option, 0)
                        poll_results[q][option] += 1
                    else:
                        poll_results.setdefault(q, {}).setdefault(a, 0)
                        poll_results[q][a] += 1
                        
        return poll_results