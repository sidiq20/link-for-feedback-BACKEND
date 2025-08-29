from flask import Blueprint, request, jsonify, g 
from backend.middleware.auth import jwt_required
from backend.models.form_links import FORM_LINK 
from backend.models.forms import FORM

form_links_bp = Blueprint("form_links", __name__)

@form_links_bp.route("/<form_id>", methods=["POST"])
@jwt_required
def create_link(form_id):
    existing_link = FORM_LINK.get_by_form_id(form_id)
    if existing_link:
        return jsonify({
            "message": "Form link already exists",
            "slug": existing_link["slug"]
        }), 200
        
    slug = FORM_LINK.create(g.current_user["_id"], form_id)
    return jsonify({"message": "Form link created", "slug": slug}), 201


@form_links_bp.route("/slug/<slug>", methods=["GET"])
def get_form_by_slug(slug):
    link = FORM_LINK.get_by_slug(slug)
    if not link:
        return jsonify({"error": "Form link invalid or expired"}), 404
    
    form = FORM.get_by_id(link["form_id"])
    if not form:
        return jsonify({"error": "Form not found"}), 404 
    
    form["_id"] = str(form["_id"])
    
    return jsonify({
        "form": form,
        "slug": link["slug"], 
        "expires_at": link["expires_at"],  
        "is_active": link["is_active"]     
    }), 200