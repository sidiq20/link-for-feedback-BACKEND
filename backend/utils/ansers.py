from backend.utils.security import decrypt_answer, normalize_answer

def load_correct_answer(stored):
    """
    Load encrypted answe (single or list)
    """
    if stored is None:
       return None
   
    if isinstance(stored, list):
        return [decrypt_answer(answer) for answer in stored]
    
    return decrypt_answer(stored)

def answers_match(user_answer, correct_answer):
    """
    Compare user answer with correct answer, handling both single and multiple answers.
    """
    norm_user = normalize_answer(user_answer)
    norm_correct = normalize_answer(correct_answer)
    
    if isinstance(norm_correct, list) and isinstance(norm_user, list):
        return sorted(norm_user) == sorted(norm_correct)
    
    if isinstance(norm_correct, dict) and isinstance(norm_user, dict):
        return norm_user == norm_correct
    
    return norm_user == norm_correct