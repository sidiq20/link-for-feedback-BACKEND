from datetime import datetime
from bson import ObjectId
from flask import current_app

class FORM:
    COLLECTION = "forms"
    
    @staticmethod
    def get_collection():
        return current_app.mongo.db[FORM.COLLECTION]
    
    @staticmethod
    def create(user_id, title, description, question):
        doc = {
            "user_id": ObjectId(user_id),
            "title": title,
            "description": description,
            "questions": question,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = FORM.get_collection().insert_one(doc)
        return str(result.insert_id)
    
    @staticmethod
    def get_by_id(form_id):
        return FORM.get_collection().find_one({"_id": ObjectId(form_id)})
    
    @staticmethod
    def get_by_user(user_id):
        return FORM.get_collection().find_one({"_id": ObjectId(user_id)})
    
    @staticmethod
    def update(form_id, update_data):
        update_data["update_at"] = datetime.utcnow()
        return FORM.get_collection().update_one(
            {"_id": ObjectId(form_id)},
            {"$set": update_data}
        )
        
    @staticmethod
    def delete(form_id):
        return FORM.get_collection().delete_one({"_id": ObjectId(form_id)})