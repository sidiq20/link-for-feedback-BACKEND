import re
import html
from email_validator import validate_email as email_validate, EmailNotValidError
from itsdangerous import URLSafeTimedSerializer

def generate_token(salt, email, secret_key):
    serializer = URLSafeTimedSerializer(secret_key)
    return serializer.dumps(email, salt=salt)

def verify_token(token, secret_key, salt, max_age=3600):
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        email = serializer.loads(token, salt=salt, max_age=max_age)
    except Exception:
        return None 
    return email

def validate_email(email):
    """Validate email address format"""
    try:
        # Validate and get normalized email
        valid = email_validate(email)
        return True, valid.email
    except EmailNotValidError:
        return False, None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    
    return True, "Password is valid"

def sanitize_input(text, max_length=None):
    """Sanitize user input to prevent XSS"""
    if not text:
        return ""
    
    # Strip whitespace and escape HTML
    sanitized = html.escape(str(text).strip())
    
    # Limit length if specified
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized

def validate_rating(rating):
    """Validate rating is between 1 and 5"""
    try:
        rating_int = int(rating)
        if 1 <= rating_int <= 5:
            return True, rating_int
        else:
            return False, None
    except (ValueError, TypeError):
        return False, None

def validate_feedback_data(data):
    """Validate complete feedback submission data"""
    errors = {}
    
    # Validate name
    name = data.get('name', '').strip()
    if not name:
        errors['name'] = 'Name is required'
    elif len(name) > 255:
        errors['name'] = 'Name must be less than 255 characters'
    
    # Validate email
    email = data.get('email', '').strip()
    if not email:
        errors['email'] = 'Email is required'
    else:
        is_valid, normalized_email = validate_email(email)
        if not is_valid:
            errors['email'] = 'Invalid email format'
        else:
            # Store the normalized email for use
            data['email'] = normalized_email
    
    # Validate rating
    rating = data.get('rating')
    is_valid_rating, rating_value = validate_rating(rating)
    if not is_valid_rating:
        errors['rating'] = 'Rating must be between 1 and 5'
    
    # Validate comment
    comment = data.get('comment', '').strip()
    if not comment:
        errors['comment'] = 'Comment is required'
    elif len(comment) > 5000:
        errors['comment'] = 'Comment must be less than 5000 characters'
    
    return errors