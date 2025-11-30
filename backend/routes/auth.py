from flask import Blueprint, request, jsonify, current_app, url_for, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timedelta
from backend.middleware.auth import token_required
from pymongo.errors import DuplicateKeyError
import logging
import jwt
import uuid
import requests
from backend.extensions import redis_client, mongo, limiter
from google.oauth2 import id_token
from backend.utils.validation import validate_email, validate_password, generate_token, verify_token
from backend.utils.mailer import send_email
from google.auth.transport.requests import Request

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)


def get_db():
    return current_app.mongo.db


# --- JWT helpers ---

def create_jwt(payload, expires_in_seconds=900):
    """Create a JWT with a jti and short expiry (default 15 minutes = 900s)."""
    payload_copy = payload.copy()
    payload_copy["exp"] = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
    payload_copy["iat"] = datetime.utcnow()
    payload_copy["jti"] = str(uuid.uuid4())
    return jwt.encode(payload_copy, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_jwt(token):
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def blacklist_access_token(jti, expires_in_seconds=None):
    """Store a token jti in redis blacklist with TTL until token expiry."""
    try:
        if not redis_client:
            return
        key = f"blacklist:{jti}"
        ttl = expires_in_seconds if expires_in_seconds else 60 * 60 * 24
        redis_client.setex(key, ttl, "1")
    except Exception:
        logger.exception("Failed to blacklist token in redis")


def is_token_blacklisted(jti):
    try:
        if not redis_client:
            return False
        return bool(redis_client.get(f"blacklist:{jti}"))
    except Exception:
        logger.exception("Redis check failed")
        return False


# wrapper that validates JWT + non-blacklisted jti and attaches user to request
from functools import wraps


def jwt_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = decode_jwt(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        jti = payload.get("jti")
        if not jti:
            return jsonify({"error": "Malformed token"}), 401

        if is_token_blacklisted(jti):
            return jsonify({"error": "Token revoked"}), 401

        # attach user id/email for handlers
        request.user_id = payload.get("user_id")
        request.user_email = payload.get("email")

        # optionally load user into g
        db = get_db()
        try:
            user = db.users.find_one({"_id": ObjectId(request.user_id), "is_active": True})
            if not user:
                return jsonify({"error": "User not found"}), 404
            g.current_user = user
        except Exception:
            return jsonify({"error": "Invalid user id in token"}), 401

        return func(*args, **kwargs)

    return wrapper


# --- Refresh token helpers ---

def set_refresh_cookie(response, refresh_token, max_age_days=7):
    secure_flag = current_app.config.get("USE_HTTPS", False)
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure_flag,
        samesite="Strict",
        max_age=max_age_days * 24 * 3600,
        path="/api/auth/refresh"
    )


def clear_refresh_cookie(response):
    response.delete_cookie("refresh_token", path="/api/auth/refresh")


def store_refresh_token_in_db(token, user_id, expires_days=7, replaced_by=None):
    db = get_db()
    doc = {
        "token": token,
        "user_id": str(user_id),
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=expires_days),
        "revoked": False,
        "replaced_by": replaced_by,
    }
    db.refresh_tokens.insert_one(doc)
    return doc


def revoke_refresh_token(token, reason="user_logout"):
    db = get_db()
    db.refresh_tokens.update_one({"token": token}, {"$set": {"revoked": True, "revoked_at": datetime.utcnow(), "revoked_reason": reason}})


def rotate_refresh_token(old_token):
    db = get_db()
    old = db.refresh_tokens.find_one({"token": old_token})
    if not old:
        return None

    if old.get("revoked"):
        return None

    # mark old revoked and create a new one
    new_token = str(uuid.uuid4())
    db.refresh_tokens.update_one({"token": old_token}, {"$set": {"revoked": True, "revoked_at": datetime.utcnow()}})
    store_refresh_token_in_db(new_token, old["user_id"])  # default 7 days
    return new_token


# --- Routes ---

@auth_bp.route("/register", methods=["POST"])
@limiter.limit('5 per minute')
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
        login_url = current_app.config.get("FRONTEND_URL", "")
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
@limiter.limit('5 per minute')
def login():
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
        if not user or not user.get("password") or not check_password_hash(user["password"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        # Create tokens
        access_token = create_jwt({"user_id": str(user["_id"]), "email": user["email"]}, expires_in_seconds=900)
        refresh_token = str(uuid.uuid4())

        # persist refresh token in DB
        store_refresh_token_in_db(refresh_token, user["_id"])

        # Optionally store session in redis: (keeps track of active sessions)
        try:
            if redis_client:
                redis_client.setex(f"user_session:{user['_id']}", 7 * 24 * 3600, refresh_token)
        except Exception:
            logger.exception("Redis session write failed")

        logger.info(f"User logged in: {identifier}")
        response = jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "user": {
                "_id": str(user["_id"]),
                "email": user["email"],
                "name": user.get("name"),
            }
        })

        set_refresh_cookie(response, refresh_token)
        return response, 200

    except Exception:
        logger.exception("Login error")
        return jsonify({"error": "Login failed"}), 500


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    try:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            return jsonify({"error": "Missing refresh token"}), 401

        db = get_db()
        stored = db.refresh_tokens.find_one({"token": refresh_token})
        if not stored:
            return jsonify({"error": "Invalid refresh token"}), 401

        if stored.get("revoked"):
            return jsonify({"error": "Refresh token revoked"}), 401

        if stored.get("expires_at") < datetime.utcnow():
            db.refresh_tokens.delete_one({"token": refresh_token})
            return jsonify({"error": "Refresh token expired"}), 401

        user = db.users.find_one({"_id": ObjectId(stored["user_id"]), "is_active": True})
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Rotate refresh token (invalidate old, issue new)
        new_refresh = rotate_refresh_token(refresh_token)
        if not new_refresh:
            return jsonify({"error": "Refresh token rotation failed"}), 401

        # Issue a new short-lived access token
        access_token = create_jwt({"user_id": str(user["_id"]), "email": user["email"]}, expires_in_seconds=900)

        # Blacklist old access token if client sent it (optional)
        # If client sends old access token in Authorization header, mark its jti as revoked
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            old_token = auth_header.split(" ", 1)[1]
            old_payload = decode_jwt(old_token)
            if old_payload and old_payload.get("jti"):
                exp = old_payload.get("exp")
                ttl = int(exp - datetime.utcnow().timestamp()) if exp else 60
                blacklist_access_token(old_payload.get("jti"), expires_in_seconds=max(ttl, 60))

        response = jsonify({"access_token": access_token})
        set_refresh_cookie(response, new_refresh)
        return response, 200

    except Exception:
        logger.exception("Refresh token error")
        return jsonify({"error": "Failed to refresh token"}), 500


@auth_bp.route("/logout", methods=["POST"])
def logout():
    try:
        # Prefer cookie-based logout: read refresh token from cookie
        refresh_token = request.cookies.get("refresh_token")

        if refresh_token:
            revoke_refresh_token(refresh_token, reason="user_logout")

        # If client provided Authorization header, blacklist access token jti
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            payload = decode_jwt(token)
            if payload and payload.get("jti"):
                exp = payload.get("exp")
                ttl = int(exp - datetime.utcnow().timestamp()) if exp else 60
                blacklist_access_token(payload.get("jti"), expires_in_seconds=max(ttl, 60))

        response = jsonify({"message": "Logged out successfully"})
        clear_refresh_cookie(response)
        return response, 200

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
            frontend_url = current_app.config.get("FRONTEND_URL", "")
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

        db.refresh_tokens.delete_many({"user_id": str(result.upserted_id)})

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
        "name": user.get("name"),
        "student": user.get("student_id") if "student_id" else None
    })


@auth_bp.route("/google", methods=["GET"])
@limiter.limit('3 per minute')
def google_auth_url():
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    redirect_uri = f"{current_app.config['BACKEND_URL']}/api/auth/google/callback"

    google_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        "&scope=openid%20email%20profile"
    )

    return jsonify({"url": google_url})


@auth_bp.route("/google/callback", methods=["GET"])
def google_callback():
    print("CALLBACK HIT!")
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing Google code"}), 400

    token_url = "https://oauth2.googleapis.com/token"
    redirect_uri = f"{current_app.config['BACKEND_URL']}/api/auth/google/callback"
    print("REDIRECT URI USED:", redirect_uri)

    data = {
        "code": code,
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    # Use requests to exchange code for tokens
    token_res = requests.post(token_url, data=data, timeout=10).json()
    logger.error("google token response:", token_res)
    print("google token response:", token_res)
    if "id_token" not in token_res:
        logger.exception(f"Google token exchange failed: {token_res}")
        return jsonify({"error": "Google token exchange failed"}), 400
    
    print("STEP 1: Starting verify...")
    print("AUDIENCE EXPECTED:", current_app.config["GOOGLE_CLIENT_ID"])
    print("GOT ID_TOKEN:", token_res["id_token"][:50], "...")
    
    # Verify Google ID token
    idinfo = id_token.verify_oauth2_token(
        token_res["id_token"],
        Request(),
        current_app.config["GOOGLE_CLIENT_ID"]
    )
    print("STEP 2: Verify passed!")
    print("IDINFO:", idinfo)

    email = idinfo.get("email")
    name = idinfo.get("name")
    google_id = idinfo.get("sub")
    email_verified = idinfo.get("email_verified", False)

    db = get_db()

    user = db.users.find_one({"email": email})

    if not user:
        # Create Google user
        user_doc = {
            "email": email,
            "name": name,
            "provider": "google",
            "google_id": google_id,
            "password": None,
            "email_verified": email_verified,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = db.users.insert_one(user_doc)
        user = db.users.find_one({"_id": result.inserted_id})

    # Generate our JWT + refresh token
    access_token = create_jwt({"user_id": str(user["_id"]), "email": user["email"]}, expires_in_seconds=900)
    refresh_token = str(uuid.uuid4())

    store_refresh_token_in_db(refresh_token, user["_id"])

    frontend_redirect = f"{current_app.config['FRONTEND_URL']}/auth/callback?access={access_token}&refresh={refresh_token}"

    return jsonify({"redirect": frontend_redirect})


@auth_bp.route("/send-verification", methods=["POST"])
@limiter.limit('3 per minute')
@token_required
def send_verification():
    try:
        user = g.current_user

        if user.get("is_verified"):
            return jsonify({"message": "Email already verified"}), 200

        token = generate_token(
            salt=current_app.config["SECURITY_PASSWORD_SALT"],
            email=user["email"],
            secret_key=current_app.config["SECRET_KEY"]
        )

        verify_url = f"{current_app.config['FRONTEND_URL']}/verify-email/{token}"

        send_email(
            subject="Verify Your Whisper Email ✔️",
            recipients=[user["email"]],
            body=f"""
        Hi {user.get('name', 'there')},

        Please verify your Whisper account email by clicking the link below:

        👉 {verify_url}

        The link expires in **30 minutes**.

        If you didn’t create this account, please ignore this message.
        """
        )

        return jsonify({"message": "Verification email sent"}), 200

    except Exception as e:
        logger.exception("Verification email error")
        return jsonify({"error": "Could not send verification email"}), 500


@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    try:
        email = verify_token(
            token=token,
            secret_key=current_app.config["SECRET_KEY"],
            salt=current_app.config["SECURITY_PASSWORD_SALT"],
            max_age=3600   # 1 hour
        )

        if not email:
            return jsonify({"error": "Invalid or expired token"}), 400

        db = get_db()
        result = db.users.update_one(
            {"email": email},
            {"$set": {"is_verified": True, "updated_at": datetime.utcnow()}}
        )

        if result.modified_count == 0:
            return jsonify({"error": "User not found"}), 404

        return jsonify({"message": "Email verified successfully"}), 200

    except Exception as e:
        logger.exception("Email verification error")
        return jsonify({"error": "Verification failed"}), 500
