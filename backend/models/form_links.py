from datetime import datetime, timedelta
from bson import ObjectId
from flask import current_app
import uuid 

class FORM_LINK:
    COLLECTION = "form_links"
    
    @staticmethod
    def get_collection():
        return current_app.mongo.db[FORM_LINK.COLLECTION]
    
    @staticmethod
    def generate_unique_slug():
        while True:
            slug = str(uuid.uuid4())[:8]
            exists = FORM_LINK.get_collection().find_one({"slug": slug})    
            if not exists:
                return slug       
                
    @staticmethod
    def create(user_id, form_id, expires_in_days=7):
        slug = FORM_LINK.generate_unique_slug()
        doc = {
            "form_id": ObjectId(form_id),
            "user_id": ObjectId(user_id), 
            "slug": slug,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=expires_in_days),
            "is_active": True
        }
        
        FORM_LINK.get_collection().insert_one(doc)
        return slug 
    
    @staticmethod
    def get_by_slug(slug):
        return FORM_LINK.get_collection().find_one({
            "slug": slug,
            "is_active": True
        })
    
    @staticmethod
    def get_by_id(form_id):
        return FORM_LINK.get_collection().find_one({"_id": ObjectId(form_id)})
    
    @staticmethod
    def deactivate(slug):
        return FORM_LINK.get_collection().update_one(
            {"slug": slug},
            {"$set": {"is_active": False}}
        )