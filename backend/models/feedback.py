from datetime import datetime, timedelta
from bson import ObjectId
from flask import current_app

class Feedback:
    COLLECTION = "feedback"

    @staticmethod
    def get_collection():
        return current_app.mongo.db[Feedback.COLLECTION]

    @staticmethod
    def create(feedback_link_id, name, email, rating, comment, ip_address=None, user_agent=None):
        doc = {
            "feedback_link_id": ObjectId(feedback_link_id),
            "name": name,
            "email": email,
            "rating": rating,
            "comment": comment,
            "submitted_at": datetime.utcnow(),
            "ip_address": ip_address,
            "user_agent": user_agent
        }
        result = Feedback.get_collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    @staticmethod
    def find_by_id(feedback_id):
        try:
            return Feedback.get_collection().find_one({"_id": ObjectId(feedback_id)})
        except Exception:
            return None

    @staticmethod
    def find_by_link(feedback_link_id, filters=None, sort_by="submitted_at", sort_order=-1, limit=None, skip=None):
        query = {"feedback_link_id": ObjectId(feedback_link_id)}
        if filters:
            query.update(filters)

        cursor = Feedback.get_collection().find(query).sort(sort_by, sort_order)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    @staticmethod
    def delete_by_id(feedback_id):
        return Feedback.get_collection().delete_one({"_id": ObjectId(feedback_id)})

    @staticmethod
    def to_dict(doc, include_email=True):
        if not doc:
            return None
        data = {
            "id": str(doc["_id"]),
            "feedback_link_id": str(doc["feedback_link_id"]),
            "name": doc["name"],
            "rating": doc["rating"],
            "comment": doc["comment"],
            "submitted_at": (
                doc["submitted_at"].isoformat()
                if isinstance(doc["submitted_at"], datetime)
                else str(doc["submitted_at"])
            )
        }
        if include_email:
            data["email"] = doc.get("email")
        return data

    @staticmethod
    def get_public_dict(doc):
        return Feedback.to_dict(doc, include_email=False)

    @staticmethod
    def get_analytics_data(feedback_link_id, days=30):
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        pipeline = [
            {
                "$match": {
                    "feedback_link_id": ObjectId(feedback_link_id),
                    "submitted_at": {"$gte": start_date, "$lte": end_date}
                }
            },
            {
                "$group": {
                    "_id": {
                        "rating": "$rating",
                        "date": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$submitted_at"
                            }
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id.date": 1, "_id.rating": 1}}
        ]

        return list(Feedback.get_collection().aggregate(pipeline))