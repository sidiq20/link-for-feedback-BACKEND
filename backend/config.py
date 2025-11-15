import os
from datetime import timedelta, datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from flask_session import Session
from pymongo import ASCENDING
from bson import ObjectId

load_dotenv()

class Config:
    
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_ENV') == 'development'
    
    
    MONGO_URI = os.getenv('MONGO_URI')
    MONGO_DB = os.getenv('MONGO_DB', 'feedback_app')
    
    RESEND_API = os.getenv('RESEND_API_KEY')
    BREVO_API = os.getenv('BREVO_API_KEY')
    
    
    SESSION_PERMANENT = False
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL')
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    BACKEND_URL = os.getenv('BACKEND_URL')
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False
    MAIL_USERNAME = os.getenv("SEND_EMAIL")
    MAIL_PASSWORD = os.getenv("SMTP_PASS")
    MAIL_DEFAULT_SENDER = os.getenv("SEND_EMAIL")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
 
    SECURITY_PASSWORD_SALT = os.getenv('SALT')
    
def ensure_ttl_indexes(mongo):
    db = mongo.db
    db.anonymous.create_index(
        [("submitted_at", 1)],
        expireAfterSeconds=7 * 24 * 60 * 60,
    )
    
    db.anonymous_links.create_index(
        [("created_at", 1)],
        expireAfterSeconds=7 * 24 * 60 * 60,
    )
    db.exams.create_index('code', unique=True)
    db.exams.create_index([('owner_id', 1)])
    db.exam_registration.create_index([('user_id', 1)])
    db.exam_session.create_index([('exam_id', 1), ('user_id', 1)])
    db.exam_results.create_index([('exam_id', 1)])
    print('✅ MongoDB indexes ensured.')
    
    
def test_mongo_connection(uri):
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("MongoDB connection successful")
    except ConnectionFailure as e:
        print(f"Mongo connection failed: {e}")
        raise e
    
    
def ensure_unique_indexes(mongo):
    mongo.db.users.create_index("email", unique=True, name="unique_email")
    mongo.db.users.create_index("name", unique=True, name="unique_name")
    
def ensure_ttl_indexes(mongo):
    """
    Ensure indexes exist for collections (TTL + unique).
    """
    db = mongo.db
    if "anonymous" in db.list_collection_names():
        db.anonymous.create_index("submitted_at", expireAfterSeconds=60*60*24*7)
    if "feedback" in db.list_collection_names():
        db.feedback.create_index("created_at", expireAfterSeconds=60*60*24*30)

    if "users" in db.list_collection_names():
        db.users.create_index([("email", ASCENDING)], unique=True, name="unique_email")
        db.users.create_index([("name", ASCENDING)], unique=True, name="unique_name")
        
    db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
    print("TTL index for refresh_tokens created")
        
def to_objectid(value):
    if isinstance(value, ObjectId):
        return value 
    return ObjectId(str(value))

def delete_expired_refresh_tokens(mongo):
    db = mongo.db
    now = datetime.utcnow()
    result = db.refresh_tokens.delete_many({
        "expires_at": {"$lt": now}
    })
    print(f"🧹 Deleted {result.deleted_count} expired refresh tokens.")