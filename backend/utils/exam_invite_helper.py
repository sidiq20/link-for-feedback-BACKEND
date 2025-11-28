from datetime import datetime
import secrets
from flask import current_app, jsonify
from bson import ObjectId
from backend.extensions import mongo


def now_utc():
    return datetime.utcnow()

def make_token():
    return secrets.token_urlsafe(32)

def log_exam_action(exam_id, action, actor_id=None, details=None):
    db = current_app.mongo.db
    entry = {
        "exam_id": ObjectId(exam_id) if not isinstance(exam_id, ObjectId) else exam_id,
        "action": action,
        "actor_id": ObjectId(actor_id) if actor_id else None,
        "timestamp": now_utc(),
        "details": details or {}
    }
    
def ensure_exam_and_owner(exam_id):
    db = current_app.mong.db
    exam = db.exams.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        return None, jsonify({"error": "Exam not found"}), 404
    return exam, None, None

def permission_defaults_for_role(role):
    # Default permission mapping by role (adjust to taste)
    role_map = {
        "owner":      {"can_edit_settings": True, "can_add_questions": True, "can_grade": True, "can_invite": True},
        "co-owner":   {"can_edit_settings": True, "can_add_questions": True, "can_grade": True, "can_invite": True},
        "moderator":  {"can_edit_settings": True, "can_add_questions": False, "can_grade": True, "can_invite": False},
        "grader":     {"can_edit_settings": False, "can_add_questions": False, "can_grade": True, "can_invite": False},
        "viewer":     {"can_edit_settings": False, "can_add_questions": False, "can_grade": False, "can_invite": False},
    }
    return role_map.get(role, role_map["viewer"]).copy()

