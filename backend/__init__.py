from flask import Flask
from flask_session import Session
from flask_cors import CORS
from datetime import timedelta
import logging
from .config import Config, test_mongo_connection
from backend.extensions import limiter, mail
from flasgger import Swagger
from dotenv import load_dotenv
import os
from flask_pymongo import PyMongo
import secrets
import uuid
from redis import Redis

load_dotenv()
mongo = PyMongo()

def create_app():
    app = Flask(__name__)
    CORS(app, origins=['http://localhost:5173', 'http://127.0.0.1:5173'])

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

    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = Redis.from_url(f"redis://{os.getenv('REDIS_URL')}")
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'feedback_app:'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.config['SECRET_KEY'] = app.config.get('SECRET_KEY') or secrets.token_hex(16)
    app.config['SESSION_COOKIE_NAME'] = app.config.get('SESSION_COOKIE_NAME', 'session')

    Session(app)

    def generate_session_id():
        return str(uuid.uuid4()).hex
    app.session_interface.generate_sid = generate_session_id

    limiter.init_app(app)
    app.extensions["limiter"] = limiter

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec_1',
                "route": '/apispec_1.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/"
    }
    Swagger(app, config=swagger_config)

    from backend.routes.auth import auth_bp
    from backend.routes.feedback_links import feedback_links_bp
    from backend.routes.feedback import feedback_bp
    from backend.routes.analytics import analytics_bp
    from backend.routes.anonymous import anonymous_bp
    from backend.routes.anonymous_links import anonymous_links_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(feedback_links_bp, url_prefix='/api/links')
    app.register_blueprint(feedback_bp, url_prefix='/api/feedback')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(anonymous_links_bp, url_prefix='/api/anonymous-links')
    app.register_blueprint(anonymous_bp, url_prefix='/api/anonymous')

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
