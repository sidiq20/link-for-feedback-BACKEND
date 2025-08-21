import os
from datetime import timedelta
from dotenv import load_dotenv
import mongoengine
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from flask_session import Session
from pymongo import ASCENDING

load_dotenv()

class Config:
    
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_ENV') == 'development'
    
    
    MONGO_URI = os.getenv('MONGO_URI')
    MONGO_DB = os.getenv('MONGO_DB', 'feedback_app')
    
    
    SESSION_PERMANENT = False
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL')
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False
    MAIL_USERNAME = os.getenv("SEND_EMAIL")
    MAIL_PASSWORD = os.getenv("SMTP_PASS")
    MAIL_DEFAULT_SENDER = os.getenv("SEND_EMAIL")


    
    SECURITY_PASSWORD_SALT = os.getenv('SALT')
    
def ensure_ttl_indexes(mongo):
    mongo.db.anonymous.create_index(
        [("submitted_at", 1)],
        expireAfterSeconds=7 * 24 * 60 * 60,
    )
    
    mongo.db.anonymous_links.create_index(
        [("created_at", 1)],
        expireAfterSeconds=7 * 24 * 60 * 60,
    )
    
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

    # Example: feedback TTL index
    if "feedback" in db.list_collection_names():
        db.feedback.create_index("created_at", expireAfterSeconds=60*60*24*30)  # 30 days

    # Users collection unique indexes
    if "users" in db.list_collection_names():
        db.users.create_index([("email", ASCENDING)], unique=True, name="unique_email")
        db.users.create_index([("name", ASCENDING)], unique=True, name="unique_name")