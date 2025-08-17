# backend/models/feedbacklinks.py
from datetime import datetime
import secrets
import string
from bson import ObjectId
from backend.extensions import mongo


class FeedbackLink:
    """Model for feedback collection links (PyMongo version)"""

    # COLLECTION = mongo.db.feedback_links
    
    @staticmethod
    def _collection():
        return mongo.db.feedback_links

    @staticmethod
    def generate_unique_slug(base_name):
        """Generate a unique slug based on the link name"""
        # Clean base name
        slug_base = ''.join(c for c in base_name.lower() if c.isalnum() or c in '-_')[:50]
        slug_base = slug_base.strip('-_')

        if not slug_base:
            slug_base = 'feedback'

        # Check if base slug exists
        if not FeedbackLink._collection().find_one({"slug": slug_base}):
            return slug_base

        # Generate with random suffix
        for _ in range(100):
            random_suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
            unique_slug = f"{slug_base}-{random_suffix}"
            if not FeedbackLink._collection().find_one({"slug": unique_slug}):
                return unique_slug

        # Fallback to timestamp
        timestamp = str(int(datetime.utcnow().timestamp()))
        return f"{slug_base}-{timestamp}"
    

    @staticmethod
    def create(name, owner_id, description=None, is_active=True):
        """Create a new feedback link"""
        slug = FeedbackLink.generate_unique_slug(name)
        now = datetime.utcnow()
        doc = {
            "name": name,
            "slug": slug,
            "description": description,
            "owner_id": ObjectId(owner_id),
            "created_at": now,
            "updated_at": now,
            "is_active": is_active,
            "submission_count": 0
        }
        result = FeedbackLink._collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    @staticmethod
    def find_by_slug(slug):
        """Find a feedback link by its slug"""
        return FeedbackLink._collection().find_one({"slug": slug})

    @staticmethod
    def find_by_id(link_id):
        """Find a feedback link by ID"""
        try:
            return FeedbackLink._collection().find_one({"_id": ObjectId(link_id)})
        except:
            return None

    @staticmethod
    def increment_submission_count(link_id):
        """Increment the submission count and update updated_at"""
        return FeedbackLink._collection().update_one(
            {"_id": ObjectId(link_id)},
            {
                "$inc": {"submission_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

    @staticmethod
    def to_dict(doc):
        """Convert MongoDB document to dictionary"""
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
