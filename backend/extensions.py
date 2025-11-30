from flask_limiter import Limiter
from flask_mail import Mail
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os
from flask_pymongo import PyMongo
from urllib.parse import urlparse
import redis
from flask_socketio import SocketIO

load_dotenv()
mail = Mail()
redis_client = None

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["2000 per day", "200 per hour"],
    storage_uri=os.getenv("REDIS_URL")
)

mongo = PyMongo()

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

def api_rate_limit(limit="10/minute"):
    def decorator(f):
        return limiter.limit(limit)(f)
    return decorator

def init_redis():
    global redis_client
    redis_url = os.getenv("REDIS_URL")
    parsed = urlparse(redis_url)
    try:
        redis_client = redis.Redis(
            host=parsed.hostname,
            port=parsed.port,
            username=parsed.username,
            password=parsed.password,
            decode_responses=True,
            ssl=False
        )
        redis_client.ping()
        print("✅ Connected to Redis Cloud successfully")
    except Exception as e:
        print("❌ Failed to connect to Redis Cloud:", e)
        redis_client = None