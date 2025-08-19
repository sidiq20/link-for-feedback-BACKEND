from datetime import datetime, timedelta
from bson import ObjectId 
from flask import current_app

class ANONYMOUS:
    COLLECTION = "anonymous"
        
    @staticmethod
    def get_collection():
        return current_app.mongo.db[ANONYMOUS.COLLECTION]
    
    @staticmethod
    def create(anonymous_link_id, message, ip_address=None, user_agent=None):
        doc = {
            "anonymous_link_id": ObjectId(anonymous_link_id),
            "comment": message,
            "submitted_at": datetime.utcnow(),
            "ip_adress": ip_address,
            "user_agent": user_agent
        }
        result = ANONYMOUS.get_collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc 
    
    @staticmethod
    def find_by_id(message_id):
        try:
            return ANONYMOUS.get_collection().find_one({"_id": ObjectId(message_id)})
        except Exception:
            return None  
        
    @staticmethod
    def find_by_link(anonymous_link_id, sort_by="submitted_at", sort_order=-1, limit=None, skip=None):
        query = {"anonymous_link_id": ObjectId(anonymous_link_id)}
        
        cursor = ANONYMOUS.get_collection().find(query).sort(sort_by, sort_order)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)
    
    @staticmethod
    def delete_by_id(message_id):
        return ANONYMOUS.get_collection().delete_one({"_id": ObjectId(message_id)})
    
    @staticmethod
    def to_dict(doc):
        if not doc:
            return None
        return {
            "id": str(doc["_id"]),
            "anonymous_link_id": str(doc["anonymous_link_id"]),
            "comment": doc.get("comment"),
            "submitted_at": (
                doc["submitted_at"].isoformat()
                if isinstance(doc["submitted_at"], datetime)
                else str(doc["submitted_at"])
            )
        }
        
    @staticmethod
    def get_public_dict(doc):
        return ANONYMOUS.to_dict(doc)