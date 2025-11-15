from typing import Any, Dict, List, Optional, Tuple, Union
from decimal import Decimal, InvalidOperation

from backend.utils.security import (
    hash_answer,
    verify_hashed_answer,
    decrypt_answer,
    normalize_answer,
    fuzzy_equal
)


def to_number_if_possible(val):
    try:
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        if isinstance(val, str):
            s = val.strip()
            return Decimal(s)
    except (InvalidOperation, ValueError):
        return None 
    return None 

def verify_answer(submitted_answer: Any, question_doc: Dict) -> Dict:
    """
    Returns structed verification result:
    {
        "auto_check": bool, when you want to auto-check
        "correct": bool/None, True, False if auto_checked else None
        "matches": depends on type
    }
    it should inculde type and hash_key
    """
    qtype = question_doc.get("type")
    stored_hash = question_doc.get("answer_key_hash")
    
    if not stored_hash:
        return {"auto_checked": False, "correct": None, "reason": "No stored hash"}
    
    if qtype == "mcq":
        if isinstance(submitted_answer, list):
            # multi-select: compare as sets of hashes
            # generare hashes for each selected option (normalize each)
            submitted_hashes = [hash_answer(s) for s in submitted_answer]
            try:
                correct = set(submitted_hashes) == set(stored_hash)
            except TypeError:
                correct = False
            return {"auto_checked": True, "correct": correct, "matches": {"submitted_hashes": submitted_hashes}}
        else:
            ok = verify_hashed_answer(submitted_answer, stored_hash)
            return {"auto_checked": True, "correct": ok, "matches": None}
        
    if qtype == "boolean":
        normalized = str(submitted_answer).strip().lower()
        if normalized in ("true", "false", "1", "0", "t", "f"):
            val = normalized in ("true", "1", "t")
            ok = verify_hashed_answer(val, stored_hash)
            return {"auto_checked": True}
        else:
            return {"auto_checked": False, "correct": None, "reason": "Could not parse boolean"}
        
    if qtype == "fill_blank":
        if isinstance(submitted_answer, str):
            try:
                encrypted = question_doc.get("answer_key_ancrypted")
                if encrypted:
                    answer_list = decrypt_answer(encrypted)
                    if not isinstance(answer_list, list):
                        answer_list = [answer_list]
                    for candidate in answer_list:
                        if fuzzy_equal(submitted_answer, candidate):
                            return {"auto_checked": True, "correct": True}
            except Exception:
                pass
            ok = verify_hashed_answer(submitted_answer, stored_hash)
            return {"auto_checked": True, "correct": ok}
        else:
            return {"auto_checked": False, "correct": None, "reason": "submitted not string"}
        
    if qtype == "text":
        if question_doc.get("answer_key_hash"):
            try:
                encrypted = question_doc.get("answer_key_encrypted")
                if encrypted:
                    excepted = decrypt_answer(encrypted)
                    if isinstance(excepted, list):
                        for e in excepted:
                            if fuzzy_equal(submitted_answer, e):
                                return {"auto_checked": True, "correct": True}
                    else:
                        if fuzzy_equal(submitted_answer, excepted):
                            return {"auto_checked": True, "correct": True}
            except Exception:
                pass
            ok = verify_hashed_answer(submitted_answer, question_doc.get("answer_key_hash"))
            return {"auto_checked": True, "correct": ok}
        else:
            return {"auto_checked": False, "correct": None}
    
    if qtype == "math":
        sub_num = to_number_if_possible(submitted_answer)
        try:
            enc = question_doc.get("answer_key_encrypted")
            if enc:
                excepted = decrypt_answer(enc)
                if isinstance(excepted, list):
                    excepted_nums = [to_number_if_possible(x) for x in excepted]
                else:
                    excepted_nums = [to_number_if_possible(excepted)]
            else:
                excepted_nums = []
        except Exception:
            excepted_nums = []
            
        if sub_num is not None and excepted_nums:
            for e in excepted_nums:
                if e is None:
                    continue
                try:
                    diff = abs(sub_num - e)
                    if diff == 0 or diff <= Decimal("le-6"):
                        return {"auto_checked": True, "correct": True}
                except Exception:
                    continue
            return {"auto_checked": True, "correct": False}
        else:
            ok = verify_hashed_answer(submitted_answer, stored_hash)
            return {"auto_checked": True, "correct": ok}
        
    if qtype in ("image_label", "file_upload", "match", "code"):
        ok = verify_hashed_answer(submitted_answer, stored_hash)
        return {"auto_checked": True, "correct": ok}
    
    return {"auto_checked": False, "correct": None, "reason": "Unknown type"}