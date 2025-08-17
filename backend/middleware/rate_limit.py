from functools import wraps
from flask import current_app

def api_rate_limit():
    return rate_limit_decorator("100 per minute")

def feedback_rate_limit():
    return rate_limit_decorator("5 per minute")

def rate_limit_decorator(limit_string):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limiter = current_app.extensions.get('limiter')
            if limiter:
                return limiter.limit(limit_string)(f)(*args, **kwargs)
            return f(*args, **kwargs)
        return wrapped
    return decorator
