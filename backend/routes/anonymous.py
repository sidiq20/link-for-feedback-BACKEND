from flask import Blueprint, request, jsonify
from backend.models.anonymous import ANONYMOUS
from backend.models.anonymous_links import ANONYMOUSLINK 
from backend.utils.validation import sanitize_input
from backend.utils.security import get_client_ip, hash_ip_address
from backend.middleware.auth import jwt_required
from bson import ObjectId
import logging

anonymous_bp = Blueprint("anonymous", __name__)
logger = logging.getLogger(__name__)

@anonymous_bp.route("/submit/<slug>", methods=["POST"])
def submit_anonymous(slug):
    link = ANONYMOUSLINK.find_by_slug(slug)
    if not link or not link.get("is_active", True):
        return jsonify({"error": "link not found"}), 404
    
    data = request.get_json() or {}
    message = sanitize_input(data.get("message", "").strip(), 2000)
    if not message:
        return jsonify({"error": "Message is required"}), 404
    
    anon = ANONYMOUS.create(
        anonymous_link_id=link["_id"],
        message=message,
        ip_address=hash_ip_address(get_client_ip()),
        user_agent=sanitize_input(request.headers.get("User-agent", ""), 500)
    )
    
    ANONYMOUSLINK.increment_submission_count(link["_id"])
    
    return jsonify({"message": "Message submitted", "id": str(anon["_id"])}), 201

@anonymous_bp.route("/message/<message_id>", methods=["GET"])
@jwt_required
def get_message_detail(message_id):
    msg = ANONYMOUS.find_by_id(message_id)
    if not msg:
        return jsonify({"error": "Not found"}), 404
    
    link = ANONYMOUSLINK.find_by_id(msg["anonymous_link_id"])
    if not link or str(link["owner_id"]) != request.user_id:
        return jsonify({"error": "Access denied"}), 403
    
    return jsonify(ANONYMOUS.to_dict(msg)), 200

@anonymous_bp.route("/<message_id>", methods=["DELETE"])
@jwt_required
def delete_message(message_id):
    msg = ANONYMOUS.find_by_id(message_id)
    if not msg:
        return jsonify({"error": "Not found"}), 404
    
    link = ANONYMOUSLINK.find_by_id(msg["anonymous_link_id"])
    if not link or str(link["owner_id"]) != request.user_id:
        return jsonify({"error": "access denied"}), 403
    
    ANONYMOUS.delete_by_id(message_id)
    ANONYMOUSLINK._collection().update_one(
        {"_id": link["_id"]},
        {"$inc": {"submission_count": -1}}
    )
    
    return jsonify({"message": "Message deleted"}), 200

@anonymous_bp.route("/public/<slug>", methods=["GET"])
@jwt_required
def get_public_messages(slug):
    link = ANONYMOUSLINK.find_by_slug(slug)
    if not link or not link.get("is_active", True):
        return jsonify({"error": "Link not found"}), 404
    
    messages = ANONYMOUS.find_by_link(link["_id"], limit=10, sort_order=1)
    return jsonify({
        "messages": [ANONYMOUS.get_public_dict(m) for m in messages],
        "link_info": {
            "name": link.get("name"),
            "description": link.get("description")
        }
    }), 200

@anonymous_bp.route("/link/<link_id>", methods=["GET"])
@jwt_required
def get_link_messages(link_id):
    """Get all messages for a specific anonymous link"""
    try:
        link = ANONYMOUSLINK.find_by_id(link_id)
        if not link:
            return jsonify({"error": "Link not found"}), 404
        
        # Verify ownership
        if str(link["owner_id"]) != request.user_id:
            return jsonify({"error": "Access denied"}), 403
        
        # Get pagination parameters
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(int(request.args.get("per_page", 20)), 100)
        
        # Fetch messages for this link
        messages = ANONYMOUS.find_by_link(
            ObjectId(link_id),
            limit=per_page,
            skip=(page - 1) * per_page,
            sort_order=-1
        )
        
        # Get total count
        total = ANONYMOUS._collection().count_documents({"anonymous_link_id": ObjectId(link_id)})
        
        return jsonify({
            "messages": [ANONYMOUS.to_dict(m) for m in messages],
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
        logger.exception(f"Get link messages error: {e}")
        return jsonify({"error": "Failed to get messages"}), 500
    
@anonymous_bp.route("/list", methods=["GET"])
@jwt_required
def list_messages():
    user_id = ObjectId(request.user_id)

    user_links = list(ANONYMOUSLINK._collection().find({"owner_id": user_id}))
    link_map = {link["_id"]: link for link in user_links} 

    link_ids = list(link_map.keys())
    messages = []
    if link_ids:
        cursor = ANONYMOUS._collection().find(
            {"anonymous_link_id": {"$in": link_ids}}
        ).sort("submitted_at", -1)
        messages = list(cursor)

    results = []
    for m in messages:
        msg_dict = ANONYMOUS.to_dict(m)
        link = link_map.get(m["anonymous_link_id"])
        if link:
            msg_dict["link_name"] = link.get("name", "Unnamed Link")
        else:
            msg_dict["link_name"] = "Unknown Link"

        results.append(msg_dict)

    return jsonify({"messages": results}), 200
