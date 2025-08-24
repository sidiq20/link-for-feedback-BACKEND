from datetime import datetime
from flask import current_app
from bson import ObjectId 

class RESPONSE:
    COLLECTION = "response" 
    
    @staticmethod
    def get_collection():
        return current_app.mongo.db[RESPONSE.COLLECTION]
    
    @staticmethod
    def create(form_id, question_index, user_id=None, session_id=None, answer=None):
        doc = {
            "form_id": ObjectId(form_id),
            "question_index": question_index,
            "user_id": ObjectId(user_id) if user_id else None,
            "session_id": session_id,
            "answer": answer,
            "created_at": datetime.utcnow()
        }
        RESPONSE.get_collection().insert_one(doc)
        return doc 
    
    @staticmethod
    def has_voted(form_id, question_index, user_id=None, session_id=None):
        query = {
            "form_id": ObjectId(form_id),
            "question_index": question_index
        }
        if user_id:
            query["user_id"] = ObjectId(user_id)
        elif session_id:
            query["session_id"] = session_id
            
        return RESPONSE.get_collection().find_one(query) is not None