from flask import Blueprint, request, jsonify, current_app, url_for, g
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timedelta
from backend.middleware.auth import token_required
from pymongo.errors import DuplicateKeyError
import logging
import jwt
import uuid

from backend.utils.validation import validate_email, validate_password, generate_token, verify_token
from backend.utils.mailer import send_email

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)



def get_db():
    return current_app.mongo.db


def create_jwt(payload, expires_in):
    payload_copy = payload.copy()
    payload_copy["exp"] = datetime.utcnow() + timedelta(seconds=expires_in)
    return jwt.encode(payload_copy, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_jwt(token):
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def jwt_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        logger.debug(f"Authorization header: {auth_header}")
        if not auth_header.startswith("Bearer "):
            logger.debug("Authorization header missing or invalid")
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        token = auth_header.split(" ")[1]
        logger.debug(f"Token received: {token}")
        payload = decode_jwt(token)
        if not payload:
            logger.debug("Invalid or expired token")
            return jsonify({"error": "Invalid or expired token"}), 401

        request.user_id = payload.get("user_id")
        logger.debug(f"user_id from token: {request.user_id}")
        return func(*args, **kwargs)

    return wrapper


@auth_bp.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        name = data.get("name", "").strip()
        password = data.get("password", "")

        if not all([name, email, password]):
            return jsonify({"error": "Email, name and password are required"}), 400

        is_valid_email, normalized_email = validate_email(email)
        if not is_valid_email:
            return jsonify({"error": "Invalid email format"}), 400      
        email = normalized_email

        is_valid_password, password_message = validate_password(password)
        if not is_valid_password:
            return jsonify({"error": password_message}), 400

        db = get_db()

        if db.users.find_one({"email": email}):
            return jsonify({"error": "User already exists"}), 400
        
        if db.users.find_one({"name": name}):
            return jsonify({"error": "Username already exists"}), 400

        user_doc = {
            "email": email,
            "name": name,
            "password": generate_password_hash(password),
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = db.users.insert_one(user_doc)
        login_url = current_app.config["FRONTEND_URL"]
        login_url = f"{login_url}/login"
        send_email(
            subject="Welcome to Whisper 🎉",
            recipients=[email],
            body=f"""
        Hi {name or 'there'},

        Welcome to **Whisper!** We’re thrilled to have you join our community.

        Your account has been successfully created. Here’s a quick recap of your details:

        - **Email:** {email}  
        - **Username:** {name}  

        You can now log in and start exploring all the tools and features Whisper has to offer:
        👉 [Log in to Your Account]({login_url})

        If you have any questions or need help, our support team is always here for you.

        Cheers,  
        **The Whisper Team**
        """
        )


        logger.info(f"New user registered: {email}")
        return jsonify({
            "message": "Registration successful",
            "user": {
                "_id": str(result.inserted_id),
                "email": email,
                "name": name
            }
        }), 201
        
    except DuplicateKeyError as e:
        if "email" in str(e):
            return jsonify({"error": "Email already exists"}), 400
        elif "name" in str(e):
            return jsonify({"error": "Username already exists"}), 400
        return jsonify({"error": "Duplicate key error"}), 400

    except Exception as e:
        logger.exception("Registration error")
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500




@auth_bp.route("/login", methods=["POST"])
def login():
    """
    User login
    ---
    tags:
      - Authentication
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: Login success
        schema:
          type: object
          properties:
            message:
              type: string
            access_token:
              type: string
            refresh_token:
              type: string
            user:
              type: object
              properties:
                _id:
                  type: string
                email:
                  type: string
                name:
                  type: string
    """
    try:
        data = request.get_json() or {}
        identifier = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not all([identifier, password]):
            return jsonify({"error": "Email and password are required"}), 400

        db = get_db()

        query = {"is_active": True}
        if "@" in identifier:
            query["email"] = identifier
        else:
            query["name"] = identifier
            
        user = db.users.find_one(query)
        if not user or not check_password_hash(user["password"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        refresh_token = str(uuid.uuid4())
        db.refresh_tokens.insert_one({
            "token": refresh_token,
            "user_id": str(user["_id"]),
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7)
        })

        access_token = create_jwt({"user_id": str(user["_id"]), "email": user["email"]}, expires_in=9000)  
        logger.info(f"User logged in: {identifier}")
        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "_id": str(user["_id"]),
                "email": user["email"],
                "name": user.get("name"),
                
            }
        }), 200

    except Exception:
        logger.exception("Login error")
        return jsonify({"error": "Login failed"}), 500



@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    try:
        data = request.get_json() or {}
        refresh_token = data.get("refresh_token", "")

        if not refresh_token:
            return jsonify({"error": "Refresh token is required"}), 400

        db = get_db()
        stored_token = db.refresh_tokens.find_one({"token": refresh_token})
        if not stored_token:
            return jsonify({"error": "Invalid refresh token"}), 401

        if stored_token["expires_at"] < datetime.utcnow():
            db.refresh_tokens.delete_one({"token": refresh_token})
            return jsonify({"error": "Refresh token expired"}), 401

        user = db.users.find_one({"_id": ObjectId(stored_token["user_id"]), "is_active": True})
        if not user:
            return jsonify({"error": "User not found"}), 404

        access_token = create_jwt({"user_id": str(user["_id"]), "email": user["email"]}, expires_in=900)

        return jsonify({"access_token": access_token}), 200

    except Exception:
        logger.exception("Refresh token error")
        return jsonify({"error": "Failed to refresh token"}), 500



@auth_bp.route("/logout", methods=["POST"])
def logout():
    try:
        data = request.get_json() or {}
        refresh_token = data.get("refresh_token", "")
        if refresh_token:
            get_db().refresh_tokens.delete_one({"token": refresh_token})

        return jsonify({"message": "Logged out successfully"}), 200
    except Exception:
        logger.exception("Logout error")
        return jsonify({"error": "Logout failed"}), 500



@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        if not email:
            return jsonify({"error": "Email is required"}), 400

        db = get_db()
        user = db.users.find_one({"email": email})
        if user:
            token = generate_token(
                salt=current_app.config["SECURITY_PASSWORD_SALT"],
                email=email,
                secret_key=current_app.config["SECRET_KEY"]
            )
            frontend_url = current_app.config["FRONTEND_URL"]
            reset_url = f"{frontend_url}/reset-password/{token}"
            name = data.get("name", "").strip()
            send_email(
                subject="Reset Your Whisper Password 🔒",
                recipients=[email],
                body=f"""
            Hi {name or 'there'},

            We received a request to reset your Whisper account password.

            You can reset it by clicking the secure link below:
            👉 {reset_url}

            This link will expire in **30 minutes** for security reasons.

            If you didn’t request this, no worries — just ignore this message, and your password will stay the same.

            Stay safe,  
            **The Whisper Team**
            """
            )





        return jsonify({"message": "If that email exists, a reset link has been sent"}), 200

    except Exception:
        logger.exception("Forgot password error")
        return jsonify({"error": "Password reset request failed"}), 500


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        data = request.get_json() or {}
        token = data.get("token", "").strip()
        new_password = data.get("password", "")

        if not token or not new_password:
            return jsonify({"error": "Token and password are required"}), 400

        db = get_db()
        if db.used_tokens.find_one({"token": token}):
            return jsonify({"error": "This reset link has already been used"}), 400

        try:
            email = verify_token(
                token=token,
                secret_key=current_app.config["SECRET_KEY"],
                salt=current_app.config["SECURITY_PASSWORD_SALT"],
                max_age=3600
            )
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 400

        if not email:
            return jsonify({"error": "Invalid or expired token"}), 400

        is_valid_password, password_message = validate_password(new_password)
        if not is_valid_password:
            return jsonify({"error": password_message}), 400

        result = db.users.update_one(
            {"email": email},
            {
                "$set": {
                    "password": generate_password_hash(new_password),
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if result.matched_count == 0:
            return jsonify({"error": "User not found"}), 404

        db.refresh_tokens.delete_many({"email": email})

        db.used_tokens.insert_one({
            "token": token,
            "email": email,
            "used_at": datetime.utcnow()
        })

        return jsonify({"message": "Password reset successful"}), 200

    except Exception as e:
        logger.exception("Reset password error")
        return jsonify({"error": "Password reset failed"}), 500


@auth_bp.route("/me", methods=["GET"])
@token_required
def get_current_user():
    user = g.current_user
    return jsonify({
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name")
    })

