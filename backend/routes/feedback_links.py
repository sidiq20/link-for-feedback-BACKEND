from flask import Blueprint, request, jsonify, current_app
from backend.middleware.auth import jwt_required
from backend.utils.validation import sanitize_input
from bson import ObjectId
import logging
from datetime import datetime
import traceback
import re
import unicodedata

def simple_slugify(value):
    value = str(value)
    value = unicodedata.normalize('NFKD', value)
    value = value.encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-zA-Z0-9-]+', '-', value).strip('-').lower()
    return value


feedback_links_bp = Blueprint("feedback_links", __name__)
logger = logging.getLogger(__name__)

def get_limiter():
    from flask import current_app
    return current_app.extensions.get("limiter")


@feedback_links_bp.route("/links", methods=["GET"])
@jwt_required
def get_user_links():
    limiter = get_limiter()
    if limiter:
        limiter.limit("100/minute")(lambda: None)()

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(int(request.args.get("per_page", 10)), 50)

        db = current_app.mongo.db
        links_cursor = db.feedback_links.find(
            {"owner": ObjectId(request.user_id)}
        ).sort("created_at", -1).skip((page - 1) * per_page).limit(per_page)

        links = list(links_cursor)
        for link in links:
            link["_id"] = str(link["_id"])
            link["owner"] = str(link["owner"])

        total = db.feedback_links.count_documents({"owner": ObjectId(request.user_id)})

        return jsonify({
            "links": links,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
                "has_prev": page > 1,
                "has_next": page * per_page < total
            }
        }), 200

    except Exception as e:
        logger.error(f"Get Links error: {str(e)}")
        return jsonify({"error": "Failed to get feedback links"}), 500


@feedback_links_bp.route("", methods=["POST"])
@jwt_required
def create_link():
    limiter = get_limiter()
    if limiter:
        limiter.limit("100/minute")(lambda: None)()

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400

        name = sanitize_input(data.get("name", "").strip(), 255)
        description = sanitize_input(data.get("description", "").strip(), 1000)

        if not name:
            return jsonify({"error": "Link name is required"}), 400

        # Generate unique slug
        slug = generate_unique_slug(name)

        db = current_app.mongo.db
        feedback_link = {
            "name": name,
            "slug": slug,
            "description": description,
            "owner": ObjectId(request.user_id),
            "is_active": True,
            "created_at": datetime.utcnow()
        }
        result = db.feedback_links.insert_one(feedback_link)
        feedback_link["_id"] = str(result.inserted_id)
        feedback_link["owner"] = str(feedback_link["owner"])

        logger.info(f"Feedback link created: {slug} by {request.user_id}")

        return jsonify({
            "message": "Feedback link created successfully",
            "link": feedback_link
        }), 201

    except Exception as e:
        print("=== FULL TRACEBACK ===")
        traceback.print_exc()
        logger.error(f"Create link error: {str(e)}")
        print("======================")
        return jsonify({"error": "Failed to create feedback link"}), 500


@feedback_links_bp.route("/<link_id>", methods=["GET"])
@jwt_required
def get_link(link_id):
    limiter = get_limiter()
    if limiter:
        limiter.limit("100/minute")(lambda: None)()

    try:
        db = current_app.mongo.db
        link = db.feedback_links.find_one({
            "_id": ObjectId(link_id),
            "owner": ObjectId(request.user_id)
        })

        if not link:
            return jsonify({"error": "Link not found or access denied"}), 404

        link["_id"] = str(link["_id"])
        link["owner"] = str(link["owner"])
        return jsonify({"link": link}), 200

    except Exception as e:
        logger.error(f"Get link error: {str(e)}")
        return jsonify({"error": "Failed to get feedback link"}), 500


@feedback_links_bp.route("/<link_id>", methods=["PUT"])
@jwt_required
def update_link(link_id):
    limiter = get_limiter()
    if limiter:
        limiter.limit("100/minute")(lambda: None)()

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400

        update_data = {}
        if "name" in data:
            name = sanitize_input(data["name"].strip(), 255)
            if not name:
                return jsonify({"error": "Link name cannot be empty"}), 400
            update_data["name"] = name

        if "description" in data:
            update_data["description"] = sanitize_input(data["description"].strip(), 1000)

        if "is_active" in data:
            update_data["is_active"] = bool(data["is_active"])

        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        db = current_app.mongo.db
        result = db.feedback_links.update_one(
            {"_id": ObjectId(link_id), "owner": ObjectId(request.user_id)},
            {"$set": update_data}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Link not found or access denied"}), 404

        logger.info(f"Feedback link updated: {link_id}")
        return jsonify({"message": "Feedback link updated successfully"}), 200

    except Exception as e:
        logger.error(f"Update link error: {str(e)}")
        return jsonify({"error": "Failed to update the link"}), 500


@feedback_links_bp.route("/<link_id>", methods=["DELETE"])
@jwt_required
def delete_link(link_id):
    limiter = get_limiter()
    if limiter:
        limiter.limit("100/minute")(lambda: None)()

    try:
        db = current_app.mongo.db
        result = db.feedback_links.update_one(
            {"_id": ObjectId(link_id), "owner": ObjectId(request.user_id)},
            {"$set": {"is_active": False}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Link not found or access denied"}), 404

        logger.info(f"Feedback link deleted: {link_id}")
        return jsonify({"message": "Feedback link deleted successfully"}), 200

    except Exception as e:
        logger.error(f"Delete link error: {str(e)}")
        return jsonify({"error": "Failed to delete feedback link"}), 500


@feedback_links_bp.route("/by-slug/<slug>", methods=["GET"])
def get_link_by_slug(slug):
    limiter = get_limiter()
    if limiter:
        limiter.limit("100/minute")(lambda: None)()

    try:
        db = current_app.mongo.db
        feedback_link = db.feedback_links.find_one({
            "slug": slug,
            "is_active": True
        })

        if not feedback_link:
            return jsonify({"error": "Feedback link not found"}), 404

        return jsonify({
            "link": {
                "name": feedback_link["name"],
                "description": feedback_link.get("description"),
                "slug": feedback_link["slug"]
            }
        }), 200

    except Exception as e:
        logger.error(f"Get link by slug error: {str(e)}")
        return jsonify({"error": "Failed to get feedback link"}), 500



def generate_unique_slug(name):
    base_slug = simple_slugify(name)
    db = current_app.mongo.db
    slug = base_slug
    counter = 1
    while db.feedback_links.find_one({"slug": slug}):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug

