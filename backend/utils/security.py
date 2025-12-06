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
import re 

logger = logging.getLogger(__name__)

FERNET_KEY = os.environ.get("FERNET_KEY")

if not FERNET_KEY:
    raise RuntimeError(
        "FERNET_KEY is missing! set it in the environment before starting the app"
    )
    
try:
    _fernet = Fernet(FERNET_KEY.encode())
except Exception as e:
    raise RuntimeError("FERNET_KEY is invalid. Must be a valid Fernet key.") from e


def get_fernet() -> Fernet:
    return _fernet

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

# true hash

def hash_answer(value: Any) -> str:
    normalized = normalize_answer(value)
    serilaized = serialize_normalized(normalized)
    return hashlib.sha256(serilaized.encode('utf-8')).hexdigest()

# encrypt password
def encrypt_answer(value: Any) -> str:
    f = get_fernet()
    payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
    token = f.encrypt(payload)
    return token.decode('utf-8')

def decrypt_answer(token: str) -> Any:
    f = get_fernet()
    try:
        payload = f.decrypt(token.encode('utf-8'))
        return json.loads(payload.decode('utf-8'))
    except InvalidToken:
        raise ValueError('Invalid encrypted answer token')
    
def verify_answer(user_answer: Any, stored_hash: Union[str, List[str]]) -> bool:
    user_h = hash_answer(user_answer)
    
    if isinstance(stored_hash, list):
        return any(hmac.compare_digest(h, user_h) for h in stored_hash)
    
    return hmac.compare_digest(stored_hash, user_h)

# csrf / misc util
def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]

def verify_csrf_token(token):
    return token and session.get("csrf_token") == token

def get_client_ip():
    if request.headers.getlist("HTTP_X_FORWARDED_FOR"):
        return request.headers.getlist("HTTP_X_FORWARDED_FOR").split(',')[0].strip()
    elif request.environ.get('HTTP_X_REAL_IP'):
        return request.environ.get('HTTP_X_REAL_IP')
    else:
        return request.environ.get('REMOTE_ADDR', 'unknown')
    
def hash_ip_address(ip_address, salt=None):
    if salt is None:
        salt = b'whisper_salt'
    
    return hashlib.sha256(salt + ip_address()).hexdigest()[:16]

def secure_comare(a, b): 
    return hmac.compare_digest(str(a), str(b))

# fuzzy mathcing helper
punct_re = re.compile(r'[^\w\s]')

def normalized_text_for_fuzzy(s: str) -> str:
    s2 = " ".join(s.strip().split().lower())
    return punct_re.sub('', s2)

def fuzzy_equal(a: str, b: str) -> bool:
    return normalized_text_for_fuzzy(a) == normalized_text_for_fuzzy(b)