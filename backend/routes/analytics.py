from flask import Blueprint, request, jsonify, current_app
from bson import ObjectId
from datetime import datetime, timedelta
from backend.middleware.auth import jwt_required
import logging

analytics_bp = Blueprint("analytics", __name__)
logger = logging.getLogger(__name__)


def get_db():
    return current_app.mongo.db



@analytics_bp.route("/feedback-trend", methods=["GET"])
@jwt_required
def feedback_trend():
    try:
        db = get_db()
        user_id = ObjectId(request.user_id)

        days = int(request.args.get("days", 30))
        since = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {"$match": {"owner": user_id, "created_at": {"$gte": since}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]

        results = list(db.feedback.aggregate(pipeline))
        trend = [{"date": r["_id"], "count": r["count"]} for r in results]

        return jsonify({"trend": trend}), 200

    except Exception as e:
        logger.exception("Feedback trend error")
        return jsonify({"error": "Failed to fetch feedback trend"}), 500


@analytics_bp.route("/link/<link_id>", methods=["GET"])
@jwt_required
def link_analytics(link_id):
    try:
        db = get_db()
        user_id = ObjectId(request.user_id)

        # Verify ownership
        link = db.feedback_links.find_one({"_id": ObjectId(link_id), "owner": user_id})
        if not link:
            return jsonify({"error": "Link not found or access denied"}), 404

        feedback_count = db.feedback.count_documents({"link_id": str(link["_id"])})

        latest_feedback = list(
            db.feedback.find({"link_id": str(link["_id"])}).sort("created_at", -1).limit(5)
        )
        for fb in latest_feedback:
            fb["_id"] = str(fb["_id"])
            fb["link_id"] = str(fb["link_id"])

        return jsonify({
            "link": {
                "id": str(link["_id"]),
                "name": link["name"],
                "slug": link["slug"]
            },
            "feedback_count": feedback_count,
            "latest_feedback": latest_feedback
        }), 200

    except Exception as e:
        logger.exception("Link analytics error")
        return jsonify({"error": "Failed to fetch link analytics"}), 500

@analytics_bp.route("/overview", methods=["GET"])
@jwt_required
def analytics_overview():
    try:
        db = get_db()
        user_id = ObjectId(request.user_id)

        # Count feedback links
        links_count = db.feedback_links.count_documents({"owner": user_id})
        active_links = db.feedback_links.count_documents({"owner": user_id, "is_active": True})

        # Get user's feedback link IDs
        user_links = list(db.feedback_links.find({"owner": user_id}, {"_id": 1}))
        link_ids = [link["_id"] for link in user_links]

        # Count feedback messages
        from backend.models.feedback import Feedback
        feedback_count = Feedback.get_collection().count_documents(
            {"feedback_link_id": {"$in": link_ids}}
        ) if link_ids else 0

        # Count anonymous links
        from backend.models.anonymous_links import ANONYMOUSLINK
        from backend.models.anonymous import ANONYMOUS

        anonymous_links_count = ANONYMOUSLINK._collection().count_documents({"owner_id": user_id})

        # Get user's anonymous link IDs
        user_anon_links = list(ANONYMOUSLINK._collection().find({"owner_id": user_id}, {"_id": 1}))
        anon_link_ids = [link["_id"] for link in user_anon_links]

        # Count anonymous messages
        anonymous_messages_count = ANONYMOUS._collection().count_documents(
            {"anonymous_link_id": {"$in": anon_link_ids}}
        ) if anon_link_ids else 0

        return jsonify({
            "links_count": links_count,
            "active_links": active_links,
            "feedback_count": feedback_count,
            "anonymous_links_count": anonymous_links_count,
            "anonymous_messages_count": anonymous_messages_count
        }), 200

    except Exception as e:
        logger.exception("Overview analytics error")
        return jsonify({"error": "Failed to fetch analytics"}), 500
