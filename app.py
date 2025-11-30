import os
from dotenv import load_dotenv
from backend import create_app
from backend.config import ensure_ttl_indexes
from backend.extensions import init_redis, socketio

load_dotenv()
app = create_app()
init_redis()

# socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
ensure_ttl_indexes(app.mongo)

if __name__ == "__main__":
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'

    print(f"Starting Flask application on {host}:{port}")
    print(f"Debug mode: {debug}")

    socketio.run(app, host=host, port=port, debug=debug)