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
    def create(user_id, form_id, expires_in_days=7):
        slug = str(uuid.uuid4())[:8]
        doc = {
            "form_id": ObjectId(form_id),
            "user_id": ObjectId(user_id),
            "slug": slug,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=expires_in_days),
            "is_active": True
        }
        
        result = FORM_LINK.get_collection().insert_one(doc)
        return slug 
    
    @staticmethod
    def get_by_slug(slug):
        return FORM_LINK.get_collection().find_one({"slug": slug, "is_activate": True})
    
    @staticmethod
    def deactivate(slug):
        return FORM_LINK.get_collection().update_one(
            {"slug": slug},
            {"$set": {"is_active": False}}
        )