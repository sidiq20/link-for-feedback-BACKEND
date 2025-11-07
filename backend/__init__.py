from flask import Flask
from flask_session import Session
from flask_cors import CORS
from datetime import timedelta
import logging
from .config import Config, test_mongo_connection, ensure_ttl_indexes, ensure_unique_indexes, delete_expired_refresh_tokens
from backend.extensions import init_redis, limiter, mail
from dotenv import load_dotenv
import os
from flask_pymongo import PyMongo
import secrets
import uuid
from redis import Redis
from flask_socketio import SocketIO
from flasgger import Swagger 
from backend.routes.exam.exam_socket import socketio


load_dotenv()
mongo = PyMongo()

socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

REDIS_URL = os.getenv("REDIS_URL")

def create_app():
    app = Flask(__name__)
    CORS(app,
         resources={r"/*": {
            "origins": [
                'http://localhost:5173',
                'http://127.0.0.1:5173',
                'https://whisper-opal.vercel.app'
            ]
        }},
        supports_credentials=True,
    )
    app.config['CORS_ALLOW_HEADERS'] = ["Content-Type", "Authorization"]
    app.config['CORS_ALLOW_METHODS'] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]


    
    app.config.from_object(Config)

    if not app.config.get('MONGO_URI'):
        raise RuntimeError("MONGO_URI not set in the environment or config")

    test_mongo_connection(app.config['MONGO_URI'])

    mongo.init_app(app, uri=f"{app.config['MONGO_URI']}/{app.config['MONGO_DB']}")

    app.mongo = mongo

    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('SEND_EMAIL')
    app.config['MAIL_PASSWORD'] = os.getenv('SMTP_PASS')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('SEND_EMAIL')
    mail.init_app(app)

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    if REDIS_URL.startswith("rediss://"):
        redis_client = Redis.from_url(REDIS_URL, ssl=True)
    else:
        redis_client = Redis.from_url(REDIS_URL)
        
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis_client
    app.config["RATELIMIT_STORAGE_URL"] = REDIS_URL
    init_redis()
    
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'feedback_app'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.config['SECRET_KEY'] = app.config.get('SECRET_KEY') or secrets.token_hex(16)
    app.config['SESSION_COOKIE_NAME'] = app.config.get('SESSION_COOKIE_NAME', 'session')



    Session(app)

    def generate_session_id():
        return str(uuid.uuid4()).hex
    ensure_ttl_indexes(app.mongo)
    ensure_unique_indexes(app.mongo)
    
    app.session_interface.generate_sid = generate_session_id

    limiter.init_app(app)
    app.extensions["limiter"] = limiter

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
     

    from backend.routes.auth import auth_bp
    from backend.routes.feedback_links import feedback_links_bp
    from backend.routes.feedback import feedback_bp
    from backend.routes.analytics import analytics_bp
    from backend.routes.anonymous import anonymous_bp
    from backend.routes.anonymous_links import anonymous_links_bp
    from backend.routes.forms import forms_bp
    from backend.routes.form_links import form_links_bp
    from backend.routes.form_response import form_response_bp
    from backend.routes.exam.exam_auth import exam_auth_bp
    from backend.routes.exam.exam_manage import exam_manage_bp
    from backend.routes.exam.exam_take import exam_take_bp
    from backend.routes.exam.exam_result import exam_result_bp
    from backend.routes.exam.exam_portal import exam_portal_bp
    from backend.routes.exam.exam_invite import exam_invite_bp
    from backend.routes.exam.exam_grading import exam_grading_bp
    from backend.routes.exam.exam_answer import exam_answer_bp
    from backend.routes.media_upload import media_upload_bp
    from backend.routes.health import health_bp
    

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(feedback_links_bp, url_prefix='/api/links')
    app.register_blueprint(feedback_bp, url_prefix='/api/feedback')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(anonymous_links_bp, url_prefix='/api/anonymous-links')
    app.register_blueprint(anonymous_bp, url_prefix='/api/anonymous')
    app.register_blueprint(forms_bp, url_prefix="/api/forms")
    app.register_blueprint(form_links_bp, url_prefix="/api/form-links")
    app.register_blueprint(form_response_bp, url_prefix="/api/form-response")
    app.register_blueprint(exam_auth_bp, url_prefix="/api/exam_auth_bp")
    app.register_blueprint(exam_manage_bp, url_prefix="/api/exam_manage")
    app.register_blueprint(exam_take_bp, url_prefix="/api/exam_take")
    app.register_blueprint(exam_result_bp, url_prefix="/api/exam_result/")
    app.register_blueprint(exam_portal_bp, url_prefix="/api/exam_portal/")
    app.register_blueprint(exam_invite_bp, url_prefix='/api/exam_invite/')
    app.register_blueprint(exam_grading_bp, url_prefix='/api/exam_grading')
    app.register_blueprint(exam_answer_bp, url_prefix='/api/exam_answer')
    app.register_blueprint(media_upload_bp, url_prefix='/api/media_upload')
    app.register_blueprint(health_bp)
    
    delete_expired_refresh_tokens(app.mongo)


    socketio.init_app(app, message_queue=app.config.get('REDIS_URL'))
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/apispec.json',
                "rule_filter": lambda rule: True,  # include all routes
                "model_filter": lambda tag: True,  # include all models
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs/"  # Swagger UI available at /docs
    }
    Swagger(app, config=swagger_config)
    


    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Resource not found'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Internal server error'}, 500

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return {'error': f'Rate limit exceeded: {e.description}'}, 429

    return app