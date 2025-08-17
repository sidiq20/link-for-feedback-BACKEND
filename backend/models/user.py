from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from backend import mongo 

USERS_COLLECTION = "users"

def create_user(email, password, name=""):
    hashed_password = generate_password_hash(password)
    user_data = {
        "email": email,
        "password": hashed_password,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "name": name  
    }
    result = mongo.db[USERS_COLLECTION].insert_one(user_data)
    return str(result.inserted_id)


def get_user_by_email(email):
    return mongo.db[USERS_COLLECTION].find_one({"email": email})

def get_user_by_id(user_id):
    from bson import ObjectId
    return mongo.db[USERS_COLLECTION].find_one({"_id": ObjectId(user_id)})

def check_user_password(user, password):
    return check_password_hash(user["password"], password)

def generate_registration_token():
    """Generate a unique registration token"""
    return secrets.token_urlsafe(32)