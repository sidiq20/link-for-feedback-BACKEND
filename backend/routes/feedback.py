from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import logging
from bson import ObjectId

from backend.utils.validation import validate_feedback_data, sanitize_input, validate_email
from backend.utils.security import get_client_ip, hash_ip_address
from backend.middleware.auth import jwt_required
from backend.extensions import api_rate_limit
from backend.models.feedback import Feedback

feedback_bp = Blueprint("feedback", __name__)
logger = logging.getLogger(__name__)


def get_db():
    return current_app.mongo.db


@feedback_bp.route("/submit/<slug>", methods=["POST"])
def submit_feedback(slug):
    try:
        db = get_db()
        feedback_link = db.feedback_links.find_one({"slug": slug, "is_active": True})
        if not feedback_link:
            return jsonify({"error": "Feedback link not found"}), 404

        data = request.get_json() or {}
        errors = validate_feedback_data(data)
        if errors:
            return jsonify({"error": errors}), 400

        is_valid_email, normalized_email = validate_email(data["email"])
        if not is_valid_email:
            return jsonify({"error": "Invalid email format"}), 400

        feedback_doc = Feedback.create(
            feedback_link_id=feedback_link["_id"],
            name=sanitize_input(data["name"].strip(), 255),
            email=normalized_email,
            rating=int(data["rating"]),
            comment=sanitize_input(data["comment"].strip(), 5000),
            ip_address=hash_ip_address(get_client_ip()),
            user_agent=sanitize_input(request.headers.get("User-Agent", ""), 500)
        )

        db.feedback_links.update_one(
            {"_id": feedback_link["_id"]},
            {"$inc": {"submission_count": 1}}
        )

        logger.info(f"Feedback submitted to {slug}: {feedback_doc['rating']}/5")
        return jsonify({
            "message": "Feedback submitted successfully",
            "feedback_id": str(feedback_doc["_id"])
        }), 201

    except Exception as e:
        logger.exception(f"Submit feedback error: {e}")
        return jsonify({"error": "Failed to submit feedback"}), 500


@feedback_bp.route("/link/<link_id>", methods=["GET"])
@api_rate_limit()
@jwt_required
def get_link_feedback(link_id):
    try:
        db = get_db()
        feedback_link = db.feedback_links.find_one({"_id": ObjectId(link_id)})
        if not feedback_link:
            return jsonify({"error": "Feedback link not found"}), 404

        # ensure ownership
        if str(feedback_link["owner"]) != request.user_id:
            return jsonify({"error": "Access denied"}), 403

        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(int(request.args.get("per_page", 20)), 100)
        sort_by = request.args.get("sort_by", "submitted_at")
        sort_order = 1 if request.args.get("sort_order", "desc") == "asc" else -1
        rating_filter = request.args.get("rating")

        filters = {}
        if rating_filter:
            try:
                rating_val = int(rating_filter)
                if 1 <= rating_val <= 5:
                    filters["rating"] = rating_val
            except ValueError:
                pass

        feedback_items = Feedback.find_by_link(
            feedback_link_id=link_id,
            filters=filters,
            sort_by=sort_by if sort_by in ["submitted_at", "rating", "name"] else "submitted_at",
            sort_order=sort_order,
            limit=per_page,
            skip=(page - 1) * per_page
        )
        total = Feedback.get_collection().count_documents({"feedback_link_id": ObjectId(link_id), **filters})

        return jsonify({
            "feedback": [Feedback.to_dict(item) for item in feedback_items],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
                "has_prev": page > 1,
                "has_next": page * per_page < total
            },
            "filters": {
                "sort_by": sort_by,
                "sort_order": "asc" if sort_order == 1 else "desc",
                "rating_filter": rating_filter
            }
        }), 200

    except Exception as e:
        logger.exception(f"Get link feedback error: {e}")
        return jsonify({"error": "Failed to get feedback"}), 500


@feedback_bp.route("/<feedback_id>", methods=["GET"])
@jwt_required
def get_feedback_detail(feedback_id):
    try:
        db = get_db()
        feedback = Feedback.find_by_id(feedback_id)
        if not feedback:
            return jsonify({"error": "Feedback not found"}), 404

        feedback_link = db.feedback_links.find_one({"_id": feedback["feedback_link_id"]})
        if not feedback_link or str(feedback_link["owner"]) != request.user_id:
            return jsonify({"error": "Access denied"}), 403

        return jsonify({"feedback": Feedback.to_dict(feedback)}), 200

    except Exception as e:
        logger.exception(f"Get feedback detail error: {e}")
        return jsonify({"error": "Failed to get feedback details"}), 500

@feedback_bp.route("/<feedback_id>", methods=["DELETE"])
@api_rate_limit()
@jwt_required
def delete_feedback(feedback_id):
    try:
        db = get_db()
        feedback = Feedback.find_by_id(feedback_id)
        if not feedback:
            return jsonify({"error": "Feedback not found"}), 404

        feedback_link = db.feedback_links.find_one({"_id": feedback["feedback_link_id"]})
        if not feedback_link or str(feedback_link["owner"]) != request.user_id:
            return jsonify({"error": "Access denied"}), 403

        db.feedback_links.update_one(
            {"_id": feedback_link["_id"]},
            {"$inc": {"submission_count": -1}}
        )
        Feedback.delete_by_id(feedback_id)

        logger.info(f"Feedback deleted: {feedback_id}")
        return jsonify({"message": "Feedback deleted successfully"}), 200

    except Exception as e:
        logger.exception(f"Delete feedback error: {e}")
        return jsonify({"error": "Failed to delete feedback"}), 500


@feedback_bp.route("/public/<slug>", methods=["GET"])
def get_public_feedback(slug):
    try:
        db = get_db()
        feedback_link = db.feedback_links.find_one({"slug": slug, "is_active": True})
        if not feedback_link:
            return jsonify({"error": "Feedback link not found"}), 404

        feedback_items = Feedback.find_by_link(
            feedback_link_id=feedback_link["_id"],
            sort_by="submitted_at",
            sort_order=-1,
            limit=10
        )

        return jsonify({
            "feedback": [Feedback.get_public_dict(doc) for doc in feedback_items],
            "link_info": {
                "name": feedback_link.get("name"),
                "description": feedback_link.get("description")
            }
        }), 200

    except Exception as e:
        logger.exception(f"Get public feedback error: {e}")
        return jsonify({"error": "Failed to get feedback"}), 500
