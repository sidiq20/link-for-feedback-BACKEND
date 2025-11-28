from flask import Blueprint, request, jsonify, current_app, g, url_for
from backend.middleware.auth import token_required
from backend.extensions import mongo, limiter
from bson import ObjectId
from datetime import datetime, timedelta
from backend.utils.mailer import send_email  # your Brevo sender
from backend.routes.exam.exam_manage import add_questions
from backend.utils.exam_invite_helper import now_utc, make_token, log_exam_action, ensure_exam_and_owner, permission_defaults_for_role

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


@exam_invite_bp.route("/<exam_id>/create", methods=['POST'])
@token_required
@limiter.limit('5 per minute')
def create_invite_link(exam_id):
    """
    Body:
    {
      "email": "invitee@example.com",
      "role": "grader" | "moderator" | "co-owner" | "viewer",
      "expires_in_minutes": 1440,      # optional time based expiry integer
      "permissions_overrides": { ... } # optional per-user booleans
    }
    behavior:
      - creates a single-use token link for the invitee email (if user exists, user_id stored).
      - deactivates any previously active invite for the same exam+email.
      - sends email with the link.
    """
    try:
        db = current_app.db 
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        role = data.get("role", "viewer")
        expires_in = data.get("expires_in_minutes") or {}
        overrides = data.get("permissions_overrides") or {}
        
        if not email:
            return jsonify({"error": "email is required"}), 400
        
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        # enforce only owner/c0-owner or users with invite permission should create invites
        actor = g.current_user # token_required should set g.current_user
        actor_id = actor.get("_id")
        # quick permission check: only owner/co-owner or those with can_invite in exam.examiners
        exam_owner_id = exam.get("owner_id")
        exam_examiners = exam.get("examiners", [])
        allowed = False
        if str(actor_id) == str(exam_owner_id):
            allowed = True 
        else:
            for ex in exam_examiners:
                ex_id = ex if isinstance(ex, ObjectId) else (ex.get("_id") if isinstance(ex, dict) else ex)
                if str(ex_id) == str(actor_id):
                    # if exam stores roles/permissions in exam.examiners as dicts...check that
                    if isinstance(ex, dict):
                        if ex.get("permissions", {}).get("can_invite") or ex.get("role") in ("owner", "co-owner"):
                            allowed = True
                    else:
                        allowed = False
                    break 
        if not allowed:
            return jsonify({"error": "not authorized to send invites"}), 403
        
        user = db.users.find_one({"email": email})
        user_id = user["_id"] if user else None 
        
        token = make_token()
        created_at = now_utc()
        expires_at = None 
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = created_at + timedelta(minutes=int(expires_in))
            
        # revoke any existing active invites for this exam+email
        db.invites.update_many(
            {"exam_id": ObjectId(exam_id), "email": email, "status": "pending"},
            {"$set": {"status": "revoked", "revoked_at": now_utc(), "revoked_by": ObjectId(actor_id)}}
        )
        
        invite_doc = {
            "exam_id": ObjectId(exam_id),
            "user_id": ObjectId(user_id) if user_id else None,
            "email": email,
            "token": token,
            "role": role,
            "permissions": {**permission_defaults_for_role(role), **(overrides or {})},
            "status": "pending",
            "created_by": created_at,
            "expires_at": expires_at,
            "accepted_at": None,
            "accepted_by": None
        }
        
        result = db.invites.insert_one(invite_doc)
        
        accept_url = url_for("exam_invite.accept_invite", token=token, _external=True)
        
        subject = f"Invitation to be an examiner for '{exam.get('title', 'Untitled Exam')}'"
        body = f"""
        Hello, you have been invited to participate as an examiner (role: {role}) for the exam "{exam.get('title', 'Untitled Exam')}".
        Please accept the invitation by clicking the link below:
        
        {accept_url}
        
        this link will {'expire at ' + expires_at.isoformat() if expires_at else 'remain valid until revoked'}.
        
        if you did not expect this, ignore this message.
        
        Thanks,
        Whisper Team
        """
        
        send_email(subject, email, body)
        
        log_exam_action(exam_id, "invite_created", actor_id, {"invite_id": str(result.inserted_id), "email": email, "role": role})
        
        return jsonify({"message": "Invite created and email sent", "invite_id": str(result.inserted_id), "accept_url": accept_url}), 201
    
    except Exception as e:
        current_app.logger.exception("create_invite_link error")
        return jsonify({"error": str(e)}), 500
    
    
@exam_invite_bp.route('/accept/<token>', methods=['GET', 'POST'])
@token_required
def accept_invite(token):
    # to accept invite by token, user must be authenticated 
    try:
        db = current_app.mongo.db
        invite = db.invites.find_one({"token": token})
        if not invite:
            return jsonify({"error": "invlid invite token"}), 404
        
        # check status/expiry
        if invite.get("status") != "pending":
            return jsonify({"error": f"Invite is not pending (status={invite.get('status')})"}), 404
        
        expires_at = invite.get("expires_at")
        if expires_at and isinstance(expires_at, datetime) and now_utc() > expires_at:
            # mark expired
            db.update_one({"_id": invite["_id"]}, {"$set": {"status": "expired", "expired_at": now_utc()}})
            log_exam_action(invite["exam_id"], "invite_expired", None, {"invite_id": str(invite["_id"])})
            return jsonify({"error": "Invite has expired"}), 400
        
        actor = g.current_user
        actor_id = actor.get("_id")
        actor_email = (actor.get("email") or "").lower()
        
        if invite.get("email") and invite.get("email").lower() != actor_email:
            return jsonify({"error": "This invite was sent to a diffrent email"}), 403
        
        exam_id = invite["exam_id"]
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        examiner_entry = {
            "_id": ObjectId(actor_id),
            "role": invite.get("role"),
            "permissions": invite.get("permissions", {}),
            "added_at": now_utc(),
            "added_by_invite": True
        }
        
        db.exams.update_one(
            {"_id": ObjectId(exam_id)},
            {"$addToSet": {"examiners": examiner_entry}}
        )
        
        # mark invite accepted
        db.invites.update_one(
            {"_id": invite["_id"]},
            {"$set": {"status": "accepted", "accepted_at": now_utc(), "accepted_by": ObjectId(actor_id)}}
        )
        
        # loggsss again
        log_exam_action(exam_id, 'invite_accepted', actor_id, {"invite_id": str(invite["_id"]), "role": invite.get("role")})
        
        return jsonify({"message": 'invite accepted', 'exam_id': str(exam_id)}), 200
    
    except Exception as e:
        current_app.logger.exception("accept_invite error")
        return jsonify({"error": str(e)}), 500
    
    

@exam_invite_bp.route('/<invite_id>/revoke', methods=['POST'])
@token_required
def revoke_invite(invite_id):
    """
    Revoke an invite by invite_id. only owner/co-owner or those with permission can revoke
    """
    try:
        db = current_app.mongo.db 
        actor = g.current_user
        actor_id = actor.get("_id")
        
        invite = db.invites.find_one({"_id": ObjectId(invite_id)})
        if not invite:
            return jsonify({'error': 'invite not found'}), 404
        
        exam = db.exams.find_one({"_id": invite["exam_id"]})
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        is_owner = str(actor_id) == str(exam.get("owner_id"))
        is_coowner = False 
        for ex in exam.get("examiners", []):
            if isinstance(ex, dict) and str(ex.get("_id")) == str(actor_id) and ex.get("role") == "co-owner":
                is_coowner = True 
                break
            
            
        if not (is_owner or is_coowner):
            return jsonify({"error": "not authorized to revoke invite"}), 403
        
        db.invites.update_one({"_id": ObjectId(invite_id)}, {"$set": {"status": 'revoked', 'revoked_at': now_utc(), "revoked_by": ObjectId(actor_id)}})
        
        log_exam_action(invite['exam_id'], 'invite_revoked', actor_id, {"invite_id": invite_id})
        
        return jsonify({"message": "Invite revoked"}), 200
    
    except Exception as e:
        current_app.logger.exception("revoke_invite error")
        return jsonify({'error': str(e)}), 500
    
    
@exam_invite_bp.route("/<exam_id>/remove_examiner", methods=["POST"])
@token_required
def remove_examiner(exam_id):
    """
    Body {"examiner_id": "<user_id>"}
    removes an examiner from an exam completely Owner cannot remove themselves via the route (special case)
    """
    try:
        db = current_app.mongo.db 
        data = request.get_json() or {}
        target_id = data.get("examiner_id")
        if not target_id:
            return jsonify({"error": "examiner_id required"}), 400
        
        actor = g.current_user
        actor_id = actor.get("_id")
        
        exam = db.exams.find_one({"_id": ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'exam not found'}), 404
        
        is_owner = str(actor_id) == str(exam.get("owner_id"))
        is_coowner = False
        for ex in exam.get("examiners", []):
            if isinstance(ex, dict) and str(ex.get("_id")) == str(actor_id) and ex.get("role") == "co-ownwer":
                is_coowner = True 
                break 
            
        if not (is_owner or is_coowner):
            return jsonify({'error': 'not autorized to remove examiner'}), 403
        
        db.exams.update_one(
            {'_id': ObjectId(exam_id)},
            {'$pull': {'examiners': {'_id': ObjectId(target_id)}}}
        )
        
        db.invites.update_many(
            {'exam_id': ObjectId(exam_id), '$or': [{'user_id': ObjectId(target_id)}, {'email': {'$in'}}]},
            {"$set": {'status': 'revoked', 'revoked_at': now_utc(), 'revoked_by': ObjectId(actor_id)}}
        )
        
        log_exam_action(exam_id, 'examiner_removed', actor_id, {'removed_examiner_id': str(target_id)})
        
        return jsonify({'message': 'Examiner removed'}), 200
    
    except Exception as e:
        current_app.logger.exception("remove_examiner error")
        return jsonify({'error': str(e)}), 500
    

@exam_invite_bp.route('/<exam_id>/update_perssions', methods=['POST'])
@token_required
def update_examiner_permissions(exam_id):
    """
    Body:
    {
        "examiner_id": '<user_id>',
        "permissions": {
            'can_add_questions': false, 'can_grade': true, ..
        }
        'role': 'grader' # optional
    }
    """
    try:
        db = current_app.mongo.db 
        data = request.get_json() or {}
        examiner_id = data.get("examiner_id")
        new_perms = data.get("permissions")
        new_role = data.get('role')
        
        if not examiner_id or not new_perms:
            return jsonify({'error': 'examiner_id and persmissions are required'}), 400
        
        actor = g.current_user
        actor_id = actor.get('_id')
        
        exam = db.exams.find_one({
            '_id': ObjectId(exam_id)
        })
        if not exam:
            return jsonify({'error': 'exam not found'}), 404
        
        # permission check: onwer or co-owner or the actor has can_edit
        is_onwer = str(actor_id) == str(exam.get("owner_id"))
        has_permission = False
        if is_onwer:
            has_permission = True
        else:
            for ex in exam.get("examiners", []):
                if isinstance(ex, dict) and str(ex.get('_id')) == str(actor_id):
                    if ex.get('role') in ('owner', 'co_owner') or ex.get('permissions', {}).get('can_edit_settings'):
                        has_permission = True 
                    break 
        
        if not has_permission:
            return jsonify({'error': 'not authorized to update persmissions'}), 403
        
        # update the examiner entry in exam.examiners (array of dicts)
        db.exams.update_one(
            {'_id': ObjectId(exam_id), 'examiners._id': ObjectId(examiner_id)},
            {'$set': {'examiners.$.permissions': new_perms, **({'examiners.$.new_role'} if new_role else {})}}
        )
        
        log_exam_action(exam_id, 'examiner_permissions_updated', actor_id, {'examiner_id': examiner_id, 'permissions': new_perms, 'role': new_role})
        
        return jsonify({'message': 'permissions updated'}), 200
    
    except Exception as e:
        current_app.logger.exception("update_examiner_permissions error")
        return jsonify({'error': str(e)}), 500
    

@exam_invite_bp.route('<exam_id>/list', methods=['GET'])
@token_required
def list_examiners_and_invite(exam_id):
    """returns examiner + pending invites (pedning invites only visible to owner and co-owner)
    Examiners see other examiners and their permissions
    """
    try:
        db = current_app.mongo.db
        exam = db.exams.find_one({'_id': ObjectId(exam_id)})
        if not exam:
            return jsonify({'error': 'Exam not found'})
        
        actor = g.current_user
        actor_id = actor.get