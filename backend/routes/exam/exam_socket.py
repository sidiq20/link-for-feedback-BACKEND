from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room
from flask import current_app, request
import jwt 
from bson import ObjectId
from datetime import datetime
from threading import Lock

socketio = SocketIO(cors_allowed_origins="*")
background_tasks = {}
_bg_lock = Lock()

# helper: validate token in query param 'token'
def verify_sw_token(token):
    try:
        payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"]),
        if not payload.get("user_id") or not payload.get("session_id"):
            return None
        return payload
    except Exception as e:
        current_app.logger.debug(f"WS token verify failed: {e}")
        return None
    
def start_session_timer(session_id):
    sid = str(session_id)
    with _bg_lock:
        if sid in background_tasks and not background_tasks[sid]["stop"]:
            return 
        ctrl = {"stop": False, "lock": Lock(), "task": None}
        background_tasks[sid] = ctrl
        
        def _task():
            current_app.logger.info(f"WS timer task started for session {sid}")
            try:
                db = current_app.mongo.db
                while True:
                    with ctrl["lock"]:
                        if ctrl["stop"]:
                            current_app.logger.info(f"WS timer task stopping (request) for {sid}")
                            
                    sess = db.exam_sessions.find_one({"_id": ObjectId(sid)})
                    if not sess:
                        current_app.logger.info(f"Session {sid} not found; stopping timer")
                        break
                    
                    expire_at = sess.get("expire_at")
                    if not expire_at:
                        socketio.sleep(2)
                        continue
                    
                    now = datetime.utcnow()
                    remaining = int((expire_at - now).total_seconds())
                    if remaining <= 0:
                        db.exam_session.update_one(
                            {"_id": ObjectId(sid), "status": {"$in": ["in_progress", "started"]}},
                            {"$set": {"status": "expired", "ended_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
                        )
                        socketio.emit('time_up', {'session_id': sid, 'ts': datetime.utcnow().isoformat()}, room=sid, namespace='/ws/exam')
                        current_app.logger.info(f"Session {sid} expired -> emitted time_up")
                        break 
                    
                    socketio.emit('time_update', {'session_id': sid, 'remaining_seconds': remaining, "ts": datetime.utcnow().isoformat()}, room=sid, namespace='/ws/exam/')
                    
                    socketio.sleep(1)
                    
            except Exception:
                current_app.logger.exception("Error in session timer background task")
            finally:
                with _bg_lock:
                    background_tasks.pop(sid, None)
                current_app.logger.info(f"WS timer task finished for session {sid}")
                
        ctrl["task"] = socketio.start_background_task(_task)
        return ctrl
    
    
def _stop_session_timer(session_id):
    sid = str(session_id)
    with _bg_lock:
        ctrl = background_tasks.get(sid)
        if not ctrl:
            return 
        with ctrl["lock"]:
            ctrl["stop"] = True
            
# socket handlers
    
@socketio.on('connect', namespace='/ws/exam')
def ws_connect():
    token = request.args.get('token')
    session_id = request.args.get('session_id') or (token and jwt.decode(token, options={"verify_signature": False}).get("session_id"))  # fallback
    payload = verify_sw_token(token) if token else None

    if not payload or not session_id or str(payload.get("session_id")) != str(session_id):
        # reject connection
        current_app.logger.info("WS connect refused: invalid token/session")
        return False

    # (Optional) verify session belongs to this user
    try:
        db = current_app.mongo.db
        sess = db.exam_sessions.find_one({"_id": ObjectId(session_id)})
        if not sess:
            current_app.logger.info(f"WS connect refused: session {session_id} not found")
            return False
        # optional: compare user id
        if str(sess.get("user_id")) != str(payload.get("user_id")):
            current_app.logger.info(f"WS connect refused: session.user mismatch")
            return False
    except Exception:
        current_app.logger.exception("WS connect verification error")
        return False

    join_room(session_id)
    emit('connected', {'message': 'connected', 'session_id': session_id, 'ts': datetime.utcnow().isoformat()}, room=session_id, namespace='/ws/exam')

    # start the timer background task for this session (if not running)
    try:
        _start_session_timer(session_id)
    except Exception:
        current_app.logger.exception("Failed to start session timer on connect")

@socketio.on('disconnect', namespace='/ws/exam')
def ws_disconnect():
    # attempt to leave all rooms (Socket.IO will manage)
    # If you want to stop timer when no participants remain, you could check room occupancy (not shown)
    current_app.logger.info(f"WS client disconnected sid={request.sid}")

@socketio.on('heartbeat', namespace='/ws/exam')
def handle_heartbeat(data):
    """
    Client periodically sends heartbeat to keep connection alive and optionally update ephemeral ping list.
    data: { session_id, ts }
    """
    try:
        session_id = data.get('session_id')
        emit('heartbeat_ack', {'ts': datetime.utcnow().isoformat()}, room=session_id, namespace='/ws/exam')
    except Exception:
        current_app.logger.exception("heartbeat error")

@socketio.on('proctor_event', namespace='/ws/exam')
def handle_proctor_event(data):
    """
    Client sends proctoring events (copy, devtools, faceaway, etc.)
    data: { session_id, type, details }
    """
    try:
        session_id = data.get('session_id')
        evt = {
            'session_id': ObjectId(session_id),
            'event_type': data.get('type'),
            'details': data.get('details', {}),
            'timestamp': datetime.utcnow()
        }
        current_app.mongo.db.proctor_logs.insert_one(evt)
        # increment violation counter (optional)
        current_app.mongo.db.exam_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$inc": {"violation_count": 1}, "$set": {"updated_at": datetime.utcnow()}}
        )
        emit('proctor_logged', {'ok': True, 'session_id': session_id}, room=session_id, namespace='/ws/exam')
    except Exception:
        current_app.logger.exception('WS proctor event error')
        # don't crash the socket

# helper: server-side push helper (callable from routes)
def push_progress_update(session_id, payload):
    """
    Emit a progress update to all clients in the session room.
    payload example: {'answered': 10, 'total': 40, 'percent': 25}
    """
    try:
        socketio.emit('progress_update', payload, room=str(session_id), namespace='/ws/exam')
    except Exception:
        current_app.logger.exception("push_progress_update failed")