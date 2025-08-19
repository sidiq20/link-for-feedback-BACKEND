from datetime import datetime 
import secrets
import string
from bson import ObjectId
from flask import current_app


class ANONYMOUSLINK:
    @staticmethod
    def _collection():
        return current_app.mongo.db.anonymous_links
    
    @staticmethod
    def generate_unique_slug(base_name):
        slug_base = ''.join(c for c in base_name.lower() if c.isalnum() or c in '-_')[:50]
        slug_base = slug_base.strip('-_')
        
        if not base_name:
            slug_base = "anonymous" 
            
        if not ANONYMOUSLINK._collection().find_one({"slug": slug_base}):
            return slug_base
        
        for _ in range(100):
            random_suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
            unique_slug = f"{slug_base}-{random_suffix}"
            if not ANONYMOUSLINK._collection().find_one({"slug": unique_slug}):
                return unique_slug
            
        timestamp = str(int(datetime.utcnow().timestamp()))
        return f"{slug_base}-{timestamp}"
    
    @staticmethod
    def create(name, owner_id, is_active=True, description=None):
        slug = ANONYMOUSLINK.generate_unique_slug(name)
        now = datetime.utcnow() 
        doc = {
            "slug": slug,
            "owner_id": ObjectId(owner_id),
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "is_active": is_active,
            "submission_count": 0
        }
        result = ANONYMOUSLINK._collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc 
    
    @staticmethod
    def find_by_slug(slug):
        return ANONYMOUSLINK._collection().find_one({"slug": slug})
    
    @staticmethod
    def find_by_id(link_id):
        try:
            return ANONYMOUSLINK._collection().find_one({"_id": ObjectId(link_id)})
        except:
            return None 
        
    @staticmethod
    def increment_submission_count(link_id):
        return ANONYMOUSLINK._collection().update_one(
            {"_id": ObjectId(link_id)},
            {
                "$inc": {"submission_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
    @staticmethod
    def to_dict(doc):
        if not doc:
            return None
        return {
            "id": str(doc["_id"]),
            "name": doc.get("name"),
            "slug": doc.get("slug"),
            "description": doc.get("description"),
            "owner_id": str(doc.get("owner_id")) if doc.get("owner_id") else None,
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
            "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
            "is_active": doc.get("is_active", True),
            "submission_count": doc.get("submission_count", 0)
        }