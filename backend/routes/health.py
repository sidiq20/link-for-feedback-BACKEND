from flask import Blueprint, jsonify, current_app
from datetime import datetime
from backend.extensions import redis_client, mail
from pymongo.errors import PyMongoError
import redis

health_bp = Blueprint("health", __name__)

@health_bp.route("/health", methods=["GET"])
def health_check():
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "mongo": False,
            "redis": False,
            "mail": False
        },
        "sessions": [],
        "summary": "OK"
    }

    # --- MongoDB check ---
    try:
        db = current_app.mongo.db
        db.command("ping")
        status["services"]["mongo"] = True
    except PyMongoError as e:
        status["services"]["mongo_error"] = str(e)
        status["summary"] = "ERROR"

    # --- Redis check ---
    try:
        if redis_client and redis_client.ping():
            status["services"]["redis"] = True
            # List all user sessions
            session_keys = redis_client.keys("user_session:*")
            status["sessions"] = [
                {
                    "key": key,
                    "ttl": redis_client.ttl(key)
                } for key in session_keys
            ]
        else:
            status["services"]["redis_error"] = "Redis client not initialized"
            status["summary"] = "ERROR"
    except redis.exceptions.ConnectionError as e:
        status["services"]["redis_error"] = str(e)
        status["summary"] = "ERROR"

    # --- Mail check ---
    try:
        if mail.state == 1:  # Initialized
            status["services"]["mail"] = True
        else:
            status["services"]["mail_error"] = "Mail not initialized"
            status["summary"] = "ERROR"
    except Exception as e:
        status["services"]["mail_error"] = str(e)
        status["summary"] = "ERROR"

    return jsonify(status), 200 if status["summary"] == "OK" else 500
