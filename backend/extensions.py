from flask_limiter import Limiter
from flask_mail import Mail
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os
from flask_pymongo import PyMongo

load_dotenv()
mail = Mail()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://" #os.environ.get("REDIS_URL")
)

mongo = PyMongo()

def api_rate_limit(limit="10/minute"):
    def decorator(f):
        return limiter.limit(limit)(f)
    return decorator
