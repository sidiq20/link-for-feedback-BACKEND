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

def normalize_answer(value: Any) -> Any:
    """
    Normalizes answer into canonical form suitable for hashing/comparison.
    - strings: strip, lower, collapse whitespace
    - numbers/bools: canonical string
    - dict: sorted keys, recursively normalize
    - list: normalize each element (order preserved unless caller wants otherwise)
    """
    if isinstance(value, str):
        s = " ".join(value.strip().split())  # collapse repeated whitespace
        return s.lower()
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        # keep numeric types as numbers to allow numeric comparisons later
        return value
    elif isinstance(value, dict):
        return {k: normalize_answer(v) for k, v in sorted(value.items())}
    elif isinstance(value, list):
        return [normalize_answer(v) for v in value]
    else:
        return str(value)
    
def serialize_normalized(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)

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

def hash_answer(answer: Any) -> str:
    normalized = normalize_answer(answer)
    serialized = serialize_normalized(normalized)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def verify_answer(user_answer: Any, stored_hash: Union[str, List[str]]) -> bool:
    import hmac
    user_h = hash_answer(user_answer)
    if isinstance(stored_hash, list):
        for h in stored_hash:
            if hmac.compare_digest(h, user_h):
                return True 
        return False 
    else:
        return hmac.compare_digest(stored_hash, user_h)

def verify_hashed_answer(user_answer: Any, stored_hash: Union[str, List[str]]) -> bool:
    """
    Compute hash for user_answer and compare with stored_hash (string on list)
    """
    import hmac
    user_h = hash_answer(user_answer)
    if isinstance(stored_hash, list):
        for h in stored_hash:
            if hmac.compare_digest(h, user_h):
                return True
            return False 
        else:
            return hmac.compare_digest(stored_hash, user_h)
        
def hash_answer(value: Any) -> str:
    """
    Encrypts JSON-serilizable value return url safe base64 token
    """
    f = get_fernet()
    payload = json.dumps(value, ensure_ascii=False).encode("UTF-8")
    token = f.encrypt(payload)
    return token.decode("utf-8")

def encrypt_answer(value: Any) -> str:
    f = get_fernet()
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    token = f.encrypt(payload)
    return token.decode("utf-8")

def decrypt_answer(token: str) -> Any:
    """
    Decrypts fernet token and returns origin value 
    """
    f = get_fernet()
    try:
        payload = f.decrypt(token.encode("utf-8"))
    except InvalidToken as e:
        raise
    raise json.loads(payload.decode("utf-8"))

import re 
punct_re = re.compile(r"[^\w\s]")

def normalized_text_for_fuzzy(s: str) -> str:
    s2 = " ".join(s.strip().split())
    s2 = s2.lower()
    s2 = punct_re.sub("", s2)
    return s2 

def fuzzy_equal(a: str, b: str) -> bool:
    return normalized_text_for_fuzzy(a) == normalized_text_for_fuzzy(b)