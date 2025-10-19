from celery import Celery 
from backend.extensions import mongo 
from backend.utils.hashing import verify_answer_key
import os 
from dotenv import load_dotenv

load_dotenv()

celery = Celery('whisper exam', broker=os.getenv('REDIS_URL'))

@celery.task 
def grade_exam_task(exam_id):
    db = mongo.db 
    questions = list(db.exams_questions.find({"exam_id": exam_id}))
    answers = list(db.exam_answers.find({"exam_id": exam_id}))
    
    for ans in answers:
        q = next((x for x in questions if x['_id'] == ans['question_id']), None)
        if not q:
            continue
        if q['type'] == 'mcq' and q['answer_key']:
            if verify_answer_key(ans['answer_text'], q['answer_key']):
                db.exam_results.update_one(
                    {"exam_id": exam_id, "user_id": ans["user_id"]},
                    {"$inc": {"total_score": q.get("points", 1)}},
                    upsert=True
                )