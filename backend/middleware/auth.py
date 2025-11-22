from functools import wraps
from flask import request, jsonify, g, current_app
from bson import ObjectId
import jwt
from backend.extensions import redis_client

# ---------------------------
# Helpers
# ---------------------------

def _get_bearer_token():
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.startswith("Bearer "):
        return None
    return auth.split("Bearer ", 1)[1].strip()

def _decode_jwt(token):
    if not token:
        return None, ("Missing token", 401)
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, ("Token expired", 401)
    except jwt.InvalidTokenError:
        return None, ("Invalid token", 401)
    except Exception as e:
        current_app.logger.exception(f"Unexpected JWT decode error: {e}")
        return None, ("Invalid token", 401)

def _is_jti_blacklisted(jti):
    if not jti:
        return False
    try:
        if not redis_client:
            return False
        # exists returns 1 if key exists
        return bool(redis_client.exists(f"blacklist:{jti}"))
    except Exception as e:
        # Don't fail hard if Redis is down; log and continue
        current_app.logger.warning(f"Redis blacklist check failed: {e}")
        return False

def _load_user(user_id):
    try:
        user = current_app.mongo.db.users.find_one({"_id": ObjectId(user_id), "is_active": True})
        return user
    except Exception as e:
        current_app.logger.exception(f"MongoDB user lookup failed: {e}")
        return None

# ---------------------------
# Decorators
# ---------------------------

def jwt_required(func):
    """
    Validate JWT, check jti blacklist, load user, and attach:
      - g.current_user -> full user document
      - request.user_id  -> string user id (for code that expects it)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _get_bearer_token()
        if not token:
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        payload, err = _decode_jwt(token)
        if err:
            msg, code = err
            return jsonify({"error": msg}), code

        user_id = payload.get("user_id")
        jti = payload.get("jti")

        if not user_id:
            return jsonify({"error": "Malformed token: missing user_id"}), 401
        if not jti:
            return jsonify({"error": "Malformed token: missing jti"}), 401

        # Blacklist check
        if _is_jti_blacklisted(jti):
            return jsonify({"error": "Token revoked"}), 401

        # Load user from DB
        user = _load_user(user_id)
        if user is None:
            return jsonify({"error": "User not found"}), 404

        # Attach contexts for compatibility with existing code
        g.current_user = user
        # attach user_id both to request and g for compatibility (some code uses request.user_id)
        try:
            # request is a proxy, setting attribute directly is fine for short-lived per-request usage
            request.user_id = str(user["_id"])
        except Exception:
            # If setting on request fails for whatever reason, still attach to g
            current_app.logger.debug("Could not set request.user_id; falling back to g.current_user only")
        # also attach on g
        g.user_id = str(user["_id"])
        g.token_payload = payload
        g.jti = jti

        return func(*args, **kwargs)

    return wrapper

def token_required(func):
    """
    Alias for jwt_required so legacy code using @token_required keeps working.
    """
    return jwt_required(func)
