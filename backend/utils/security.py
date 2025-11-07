import secrets 
import hashlib
import hmac
from flask import session, request 
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken
from typing import Any, List, Union
import logging
import json 
import os 
import base64

logger = logging.getLogger(__name__)

FERNET_KEY = os.environ.get("FERNET_KEY")
if not FERNET_KEY:
    FERNET_KEY = Fernet.generate_key().decode()
    logger.warning(
        "FERNET_KEY not found in environment. Generated ephemeral key — "
        "this is fine for dev but *must* be set in production!"
    )
    
def get_fernet() -> Fernet:
    return Fernet(FERNET_KEY.encode())




def generate_csrf_token():
    """Generate csrf token for forms """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]

def verify_csrf_token(token):
    """Verofy CSRF token """
    return token and session.get("csrf_token") == token 

def get_client_ip():
    """Get client IP address, handling proxies"""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    elif request.environ.get('HTTP_X_REAL_IP'):
        return request.environ['HTTP_X_REAL_IP']
    else:
        return request.environ.get('REMOTE_ADDR', 'unknown')
    
def hash_ip_address(ip_address, salt=None):
    """Hash IP adress for privacy while maintaining uniqueness"""
    if salt is None:
        salt = b"feedback_app_salt" 
        
    return hashlib.sha256(salt + ip_address.encode()).hexdigest()[:16]

def secure_compare(a, b):
    """Securely compare two strings to prevent timing attacks"""
    return hmac.compare_digest(str(a), str(b)) 

def hash_answer(answer_text: str) -> str:
    return generate_password_hash(answer_text)

def verify_answer(stored_hash: str, user_answer: str) -> bool:
    return check_password_hash(stored_hash, user_answer)