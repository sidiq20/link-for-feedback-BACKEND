from functools import wraps
from flask import session, jsonify, request, current_app, g
from bson import ObjectId
from datetime import datetime, timezone
import jwt
import os
from pymongo import MongoClient
from backend.extensions import redis_client  # ✅ import the initialized Redis client


# Mongo client (if not already managed elsewhere)
client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB")]


# ------------------ JWT HELPERS ------------------ #

def extract_token_from_header():
    """Safely extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split("Bearer ")[1].strip()


def verify_jwt(token):
    """Decode and validate a JWT token using the app's secret key."""
    if not token:
        return jsonify({"error": "Missing token"}), 401
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401


# ------------------ DECORATORS ------------------ #

def _verify_token_core():
    """Internal helper to verify JWT and session fallback."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401

    token = auth_header.split("Bearer ")[1].strip()

    # Step 1: Verify JWT signature and expiration
    try:
        decoded = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    user_id = decoded.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid token: missing user_id"}), 401

    # Step 2: Try to verify active session in Redis
    redis_ok = False
    try:
        if redis_client:
            redis_token = redis_client.get(f"user_session:{user_id}")
            if isinstance(redis_token, bytes):
                redis_token = redis_token.decode()

            if redis_token and redis_token == token:
                redis_ok = True
    except Exception as e:
        current_app.logger.warning(f"⚠️ Redis check failed, fallback to Mongo: {e}")

    # Step 3: Fallback to MongoDB if Redis fails or user not cached
    user = None
    try:
        user = current_app.mongo.db.users.find_one({"_id": ObjectId(user_id)})
    except Exception as e:
        current_app.logger.error(f"MongoDB user fetch failed: {e}")
        return jsonify({"error": "User lookup failed"}), 500

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Step 4: Security enforcement — require Redis confirmation if available
    if not redis_ok and redis_client:
        return jsonify({"error": "Session expired or invalid"}), 401

    # Attach user to context for downstream use
    g.current_user = user
    g.token_payload = decoded
    return None  # means all good


def jwt_required(f):
    """Decorator for verifying JWT (gracefully uses Mongo fallback)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        result = _verify_token_core()
        if result is not None:
            return result
        return f(*args, **kwargs)
    return decorated


def token_required(f):
    """Same as jwt_required but enforces Redis session when available."""
    @wraps(f)
    def decorated(*args, **kwargs):
        result = _verify_token_core()
        if result is not None:
            return result
        return f(*args, **kwargs)
    return decorated

def require_auth(f):
    """Decorator to require user authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        
        try:
            user = current_app.mongo.db.users.find_one({
                "_id": ObjectId(session['user_id']),
                "is_active": True
            })
            if not user:
                session.clear()
                return jsonify({'error': 'Invalid session'}), 401

            # Attach user to request context
            request.current_user = user

        except Exception:
            session.clear()
            return jsonify({'error': 'Authentication error'}), 401

        return f(*args, **kwargs)
    return decorated_function

def require_ownership(collection_name, param_name='id'):
    """Decorator to require ownership of a resource in a given collection"""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            resource_id = kwargs.get(param_name) or request.view_args.get(param_name)
            if not resource_id:
                return jsonify({'error': 'Resource ID required'}), 400

            try:
                resource = current_app.mongo.db[collection_name].find_one({
                    "_id": ObjectId(resource_id),
                    "owner": ObjectId(request.current_user["_id"])
                })

                if not resource:
                    return jsonify({'error': 'Resource not found or access denied'}), 404

                request.current_resource = resource

            except Exception:
                return jsonify({'error': 'Invalid resource ID'}), 400

            return f(*args, **kwargs)
        return decorated_function
    return decorator
