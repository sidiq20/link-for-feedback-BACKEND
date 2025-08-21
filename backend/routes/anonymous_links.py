from flask import Blueprint, request, jsonify
from backend.middleware.auth import jwt_required
from backend.utils.validation import sanitize_input
from backend.models.anonymous_links import ANONYMOUSLINK
from bson import ObjectId
import logging

anonymous_links_bp = Blueprint("anonymous_links", __name__)
logger = logging.getLogger(__name__)

@anonymous_links_bp.route("/list", methods=["GET"])
@jwt_required
def get_user_anonymous_links():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(int(request.args.get("per_page", 10)), 50)
        
        links_cursor = ANONYMOUSLINK._collection().find(
            {"owner_id": ObjectId(request.user_id)}
        ).sort("created_at", -1).skip((page - 1) * per_page).limit(per_page)
        
        links = []
        for link in links_cursor:
            link_dict = ANONYMOUSLINK.to_dict(link)
            links.append(link_dict)
        
        total = ANONYMOUSLINK._collection().count_documents({"owner_id": ObjectId(request.user_id)})
        
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
        logger.error(f"Get anonymous links error: {str(e)}")
        return jsonify({"error": "Failed to get anonymous links"}), 500

@anonymous_links_bp.route("/create", methods=["POST"]) 
@jwt_required
def create_link():
    data = request.get_json() or {}
    name = sanitize_input(data.get("name", "").strip(), 255)
    description = sanitize_input(data.get("description", "").strip(), 1000)
    
    if not name:
        return jsonify({"error": "Link name is required"}), 400 
    
    link = ANONYMOUSLINK.create(
        name=name,
        owner_id=request.user_id,
        description=description
    )
    
    return jsonify({"message": "Anonymous link created", "link": ANONYMOUSLINK.to_dict(link)}), 201

@anonymous_links_bp.route("/id/<link_id>", methods=["GET"])
def get_link(link_id):
    link = ANONYMOUSLINK.find_by_id(link_id)
    if not link or not link.get("is_acitve", True):
        return jsonify({"error": "Anonymous link not found"}), 404
    
    public_data = {
        "name": link.get("name"),
        "slug": link.get("slug"),
        "dexription": link.get("description"),
        "created_at": link.get("created_at").isoformat() if link.get("created_at") else None,
        "is_active": link.get("is_active", True)
    }
    return jsonify(public_data), 200


@anonymous_links_bp.route("/slug/<slug>", methods=["GET"])
def get_public_link(slug):
    link = ANONYMOUSLINK.find_by_slug(slug)
    if not link or not link.get("is_active", True):
        return jsonify({"error": "Anonymous link not found"}), 404

    public_data = {
        "name": link.get("name"),
        "slug": link.get("slug"),
        "description": link.get("description"),
        "created_at": link.get("created_at").isoformat() if link.get("created_at") else None,
        "is_active": link.get("is_active", True)
    }
    return jsonify(public_data), 200


@anonymous_links_bp.route("/<link_id>", methods=["PUT"])
@jwt_required
def update_link(link_id):
    data = request.get_json() or {}
    update_data = {}
    
    if "name" in data:
        update_data["name"] = sanitize_input(data["name"], 255)
    if "description" in data:
        update_data["description"] = sanitize_input(data["description"], 1000)
    if "is_active" in data:
        update_data["is_active"] = bool(data["is_active"])
        
    result = ANONYMOUSLINK._collection().update_one(
        {"_id": ObjectId(link_id), "owner_id": ObjectId(request.user_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        return jsonify({"error": "Link not found or access denied"}), 404 
    
    return jsonify({"message": "anonymous link updated"}), 200

@anonymous_links_bp.route("/<link_id>", methods=["DELETE"])
@jwt_required
def delete_link(link_id):
    # First check if link exists and user owns it
    link = ANONYMOUSLINK._collection().find_one(
        {"_id": ObjectId(link_id), "owner_id": ObjectId(request.user_id)},
    )
    
    if not link:
        return jsonify({"error": "Link not found or access denied"}), 404
    
    # Delete all messages associated with this link
    from backend.models.anonymous import ANONYMOUS
    ANONYMOUS._collection().delete_many({"anonymous_link_id": ObjectId(link_id)})
    
    # Delete the link itself
    result = ANONYMOUSLINK._collection().delete_one({"_id": ObjectId(link_id)})
    
    if result.deleted_count == 0:
        return jsonify({"error": "Link not found or access denied"}), 404
    
    return jsonify({"message": "Link deleted successfully"}), 200