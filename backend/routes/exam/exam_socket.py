from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room
from flask import current_app, request
import jwt 
from bson import ObjectId
from datetime import datetime

socketio = SocketIO(cors_allowed_origins="*")

# helper: validate token in query param 'token'
def verify_sw_token(token):
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"]),
        algorithims=["HS256"]
        return payload
    except Exception:
        return None
    
@socketio.on('connect', namespace='ws/exam')
def handle_connect():
    token = request.args.get('token')
    session_id = request.args.get('session_id')
    payload = verify_sw_token(token)
    if not payload:
        return False # reject
    # optional: verify session belongs to user in payload
    join_room(session_id)
    emit('connected', {'message': 'connected', 'ts': datetime.utcnow().isoformat()}, room=session_id)
    
@socketio.on('heartbeat', namespace='/ws/exam')
def handle_heartbeat(data):
    # data: { session_id, ts }
    session_id = data.get('session_id')
    # we might update ephemeral ping store in redis; for now ack
    emit('heartbeat_ack', {'ts': datetime.utcnow().isoformat()}, room=session_id)
    
@socketio.on("proctor_event", namespace='ws/exam')
def handle_request_event(data):
    # data Example: { session_id, type: 'blue'|'copy'|'devtools', details: {...}}
    try: 
        session_id = data.get('session_id')
        evt = {
            'session_id': ObjectId(session_id),
            'event_type': data.get('type'),
            'details': data.get('details', {}),
            'timestamp': datetime.utcnow()
        }
        current_app.mongo.db.protor_logs.insert_one(evt)
        # optional count violations
        emit('proctor_logged', {'ok': True}, room=session_id)
    except Exception:
        current_app.logger.exception('WS proctor event error')