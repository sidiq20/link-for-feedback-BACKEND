from functools import wraps
from flask import session, jsonify, request, current_app, g
from bson import ObjectId
from functools import wraps 
from datetime import datetime, timezone
import jwt 
import os 
from pymongo import MongoClient

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB")]


def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        user_id = payload.get("user_id")
        if not user_id:
            return jsonify({"error": "Invalid token required"}), 401

        user = current_app.mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404


        g.current_user = user
        request.user_id = str(user["_id"])
        return f(*args, **kwargs)
    return decorated

def token_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]  # "Bearer <token>"

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        try:
            data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = data.get("user_id")
            user = current_app.mongo.db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return jsonify({"error": "User not found"}), 404
            g.current_user = user  # ✅ set the user here
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except Exception as e:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return wrapper


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
                    return jsonify({
                        'error': 'Resource not found or access denied'
                    }), 404

                # Attach resource to request context
                request.current_resource = resource

            except Exception:
                return jsonify({'error': 'Invalid resource ID'}), 400

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_current_user():
    """Get current authenticated user"""
    if 'user_id' not in session:
        return None
    
    try:
        return current_app.mongo.db.users.find_one({
            "_id": ObjectId(session['user_id']),
            "is_active": True
        })
    except:
        return None
