import os
from datetime import timedelta
from dotenv import load_dotenv
import mongoengine
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from flask_session import Session

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
    
    MAIL_SERVER = os.getenv('SMTP_SERVER')
    MAIL_PORT = os.getenv('PORT')
    SEND_EMAIL = os.getenv('SEND_EMAIL')
    SMTP_PASS = os.getenv('SMTP_PASS')  
    SECRET_KEY = str(os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production'))
    SESSION_COOKIE_NAME = str(os.getenv('SESSION_COOKIE_NAME', 'session'))

    
    SECURITY_PASSWORD_SALT = os.getenv('SALT')
    
    
def test_mongo_connection(uri):
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("MongoDB connection successful")
    except ConnectionFailure as e:
        print(f"Mongo connection failed: {e}")
        raise e
    
