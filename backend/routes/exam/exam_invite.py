from flask import Blueprint, request, jsonify, current_app, g, url_for
from backend.middleware.auth import token_required
from backend.extensions import mongo, limiter
from bson import ObjectId
from datetime import datetime
from backend.utils.mailer import send_email  # your Brevo sender
from backend.routes.exam.exam_manage import add_questions

exam_invite_bp = Blueprint('exam_invite', __name__, url_prefix='/api/exam/invite')


# --- SEARCH USERS BY EMAIL ---
@exam_invite_bp.route('/search', methods=['GET'])
@token_required
def search_user_by_email():
    """
    Query: ?email=<email>
    Search users by email for examiner invitation.
    """
    try:
        email_query = request.args.get("email", "").strip().lower()
        if not email_query:
            return jsonify({"error": "email query required"}), 400

        db = current_app.mongo.db
        users = list(
            db.users.find(
                {"email": {"$regex": f"^{email_query}", "$options": "i"}},
                {"_id": 1, "email": 1, "name": 1}
            ).limit(10)
        )

        results = [
            {"id": str(u["_id"]), "email": u["email"], "name": u.get("name")}
            for u in users
        ]
        return jsonify({"results": results}), 200

    except Exception as e:
        current_app.logger.exception("Search user error")
        return jsonify({"error": "Failed to search users", "details": str(e)}), 500


# --- INVITE EXAMINERS ---
@exam_invite_bp.route('/<exam_id>', methods=['POST'])
@token_required
@limiter.limit('3 per minute')
def invite_examiner(exam_id):
    """
    Body: { "examiner_emails": ["john@example.com", "jane@example.com"] }
    Sends invitations and emails.
    """
    try:
        data = request.get_json() or {}
        examiner_emails = data.get('examiner_emails', [])

        if not examiner_emails:
            return jsonify({'error': 'examiner_emails required'}), 400

        db = current_app.mongo.db
        exams = db.exams
        users = db.users

        # Validate exam
        exam = exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'}), 404

        invited_list = []

        for email in examiner_emails:
            email = email.strip().lower()
            user = users.find_one({"email": email})
            if not user:
                current_app.logger.warning(f"User with email {email} not found, skipping.")
                continue

            invite_data = {
                "user_id": user["_id"],
                "email": user["email"],
                "status": "invited",
                "invited_at": datetime.utcnow()
            }

            # Add to exam.invited_examiners
            exams.update_one(
                {"_id": exam["_id"]},
                {"$addToSet": {"invited_examiners": invite_data}}
            )
            invited_list.append(user["email"])

            # Send email notification via Brevo
            dashboard_url = url_for("exam_manage.add_questions", exam_id=str(exam["_id"]), _external=True)
            subject = f"You’ve been invited as an examiner for {exam.get('title', 'an exam')}"
            body = f"""
            Hello {user.get('name', '') or 'there'},

            You’ve been selected to serve as an **Examiner** for the exam titled **"{exam.get('title', 'Untitled Exam')}"** on the Whisper platform.

            Please log in to your dashboard to review the details and manage your invitation:
            👉 [Go to Dashboard]({dashboard_url if 'dashboard_url' in locals() else '#'}).

            We’re excited to have you contribute your expertise to ensure the success of this exam.

            Best regards,  
            **The Whisper Team**
            """

            send_email(subject, user["email"], body)

        if not invited_list:
            return jsonify({'message': 'No valid users found to invite'}), 400

        return jsonify({'message': 'Examiners invited successfully', 'invited': invited_list}), 200

    except Exception as e:
        current_app.logger.exception('Invite examiner error')
        return jsonify({'error': str(e)}), 500
