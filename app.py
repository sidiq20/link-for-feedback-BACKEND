# app.py
import os
from backend import create_app, socketio
from dotenv import load_dotenv
from backend.config import ensure_ttl_indexes


load_dotenv()
app = create_app()

ensure_ttl_indexes(app.mongo)

if __name__ == "__main__":
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    socketio.run(app, host, port)
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"Starting Flask application on {host}:{port}")
    print(f"Debug mode: {debug}")
    
    app.run(host=host, port=port, debug=debug, threaded=True)