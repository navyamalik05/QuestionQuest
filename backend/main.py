from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any
from database import SessionLocal, Question, Assessment, Submission, AdminUser
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError

load_dotenv()

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

JWT_SECRET       = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = 12

# Bootstrap admin — used ONLY on first startup when no admins exist yet.
# Set these in your .env file OR Render environment variables.
# Defaults are provided so the app works out of the box locally.
BOOTSTRAP_NAME     = os.getenv("ADMIN_BOOTSTRAP_NAME",     "Admin")
BOOTSTRAP_EMAIL    = os.getenv("ADMIN_BOOTSTRAP_EMAIL",    "admin@localhost")
BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "Justice_2026!")

# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

import bcrypt as _bcrypt

def hash_password(pw: str) -> str:
    return _bcrypt.hashpw(pw.encode('utf-8'), _bcrypt.gensalt()).decode('utf-8')

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def create_token(admin_id: int, email: str) -> str:
    payload = {
        "sub": str(admin_id),
        "email": email,
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def require_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload  = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        admin_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(
            AdminUser.id == admin_id,
            AdminUser.is_active == True
        ).first()
        if not admin:
            raise HTTPException(status_code=401, detail="Admin not found or inactive")
        return admin
    finally:
        db.close()

# ─────────────────────────────────────────────
# App + CORS
# ─────────────────────────────────────────────

app = FastAPI(title="QuestionQuest API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Bootstrap: create first admin on startup
# ─────────────────────────────────────────────

@app.on_event("startup")
def bootstrap_admin():
    """If NO admins exist yet, create one automatically."""
    db = SessionLocal()
    try:
        if db.query(AdminUser).count() == 0:
            admin = AdminUser(
                name=BOOTSTRAP_NAME,
                email=BOOTSTRAP_EMAIL.lower().strip(),
                password_hash=hash_password(BOOTSTRAP_PASSWORD),
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"Bootstrap admin created: {BOOTSTRAP_EMAIL}  /  password: {BOOTSTRAP_PASSWORD}")
        else:
            print("Admin users already exist — skipping bootstrap.")
    finally:
        db.close()

# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "QuestionQuest API is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class AdminLoginIn(BaseModel):
    name:     str = ""
    email:    str
    password: str

class QuestionIn(BaseModel):
    text:       str
    type:       str
    options:    List[Any] = []
    correct:    str = ""
    category:   str = ""
    difficulty: str = "Intermediate"

class AssessmentIn(BaseModel):
    title:        str
    description:  str = ""
    question_ids: List[int] = []
    group:        str = ""
    status:       str = "Draft"

class AssessmentUpdate(BaseModel):
    title:        Optional[str]       = None
    description:  Optional[str]       = None
    question_ids: Optional[List[int]] = None
    group:        Optional[str]       = None
    status:       Optional[str]       = None

class SubmissionIn(BaseModel):
    candidate:     str
    email:         str
    assessment_id: int
    answers:       dict

class AdminUserIn(BaseModel):
    name:     str
    email:    str
    password: str

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def safe_loads(val, fallback="[]"):
    try:
        return json.loads(val or fallback)
    except Exception:
        return json.loads(fallback)

def normalize(val):
    return str(val or "").strip().lower().replace(" ", "")

# ─────────────────────────────────────────────
# Admin auth
# ─────────────────────────────────────────────

@app.post("/admin-login")
def admin_login(data: AdminLoginIn):
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(
            AdminUser.email     == data.email.lower().strip(),
            AdminUser.is_active == True,
        ).first()
        if not admin or not verify_password(data.password, admin.password_hash):
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
        token = create_token(admin.id, admin.email)
        return {
            "success": True,
            "token": token,
            "admin": {"id": admin.id, "name": admin.name, "email": admin.email},
        }
    finally:
        db.close()

# ─────────────────────────────────────────────
# Admin users
# ─────────────────────────────────────────────

@app.get("/admin-users")
def list_admin_users(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        return [
            {
                "id":        a.id,
                "name":      a.name,
                "email":     a.email,
                "is_active": a.is_active,
                "created_at": str(a.created_at),
            }
            for a in db.query(AdminUser).order_by(AdminUser.created_at.desc()).all()
        ]
    finally:
        db.close()

@app.post("/admin-users")
def create_admin_user(data: AdminUserIn, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        if db.query(AdminUser).filter(AdminUser.email == data.email.lower().strip()).first():
            raise HTTPException(status_code=400, detail="Email already registered as admin")
        admin = AdminUser(
            name=data.name.strip(),
            email=data.email.lower().strip(),
            password_hash=hash_password(data.password),
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        return {"id": admin.id, "name": admin.name, "email": admin.email, "message": "Admin created"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.delete("/admin-users/{admin_id}")
def deactivate_admin_user(admin_id: int, current_admin: AdminUser = Depends(require_admin)):
    if current_admin.id == admin_id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        admin.is_active = False
        db.commit()
        return {"message": "Admin deactivated"}
    finally:
        db.close()

# ─────────────────────────────────────────────
# Questions
# ─────────────────────────────────────────────

@app.get("/questions")
def get_questions(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        return [
            {
                "id":         q.id,
                "text":       q.text,
                "type":       q.type,
                "options":    safe_loads(q.options, "[]"),
                "correct":    q.correct,
                "category":   q.category,
                "difficulty": q.difficulty,
            }
            for q in db.query(Question).all()
        ]
    finally:
        db.close()

@app.post("/questions")
def create_question(q: QuestionIn, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        item = Question(
            text=q.text,
            type=q.type,
            options=json.dumps(q.options),
            correct=q.correct,
            category=q.category,
            difficulty=q.difficulty,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "message": "Question created"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.delete("/questions/{qid}")
def delete_question(qid: int, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        q = db.query(Question).filter(Question.id == qid).first()
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")
        db.delete(q)
        db.commit()
        return {"message": "Deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# ─────────────────────────────────────────────
# Assessments  (admin routes)
# ─────────────────────────────────────────────

@app.get("/assessments")
def list_assessments(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        return [
            {
                "id":           a.id,
                "title":        a.title,
                "description":  a.description or "",
                "question_ids": safe_loads(a.question_ids, "[]"),
                "group":        a.group_name or "",
                "status":       a.status or "Draft",
            }
            for a in db.query(Assessment).all()
        ]
    finally:
        db.close()

@app.post("/assessments")
def create_assessment(a: AssessmentIn, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        row = Assessment(
            title=a.title.strip(),
            description=a.description.strip(),
            question_ids=json.dumps(a.question_ids),
            group_name=a.group.strip(),
            status=a.status or "Draft",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "message": "Assessment created"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.put("/assessments/{aid}")
def update_assessment(aid: int, data: AssessmentUpdate, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        a = db.query(Assessment).filter(Assessment.id == aid).first()
        if not a:
            raise HTTPException(status_code=404, detail="Assessment not found")
        if data.title        is not None: a.title        = data.title.strip()
        if data.description  is not None: a.description  = data.description.strip()
        if data.question_ids is not None: a.question_ids = json.dumps(data.question_ids)
        if data.group        is not None: a.group_name   = data.group.strip()
        if data.status       is not None: a.status       = data.status.strip()
        db.commit()
        return {"message": "Updated"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.delete("/assessments/{aid}")
def delete_assessment(aid: int, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        a = db.query(Assessment).filter(Assessment.id == aid).first()
        if not a:
            raise HTTPException(status_code=404, detail="Assessment not found")
        db.delete(a)
        db.commit()
        return {"message": "Deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# ─────────────────────────────────────────────
# Assessments  (public routes — students)
# NOTE: /assessments/by-group/{group_name} MUST come before /assessments/{aid}
# so FastAPI doesn't treat "by-group" as an integer ID.
# ─────────────────────────────────────────────

@app.get("/assessments/by-group/{group_name}")
def get_assessments_for_group(group_name: str):
    db = SessionLocal()
    try:
        rows = db.query(Assessment).filter(
            Assessment.group_name == group_name.strip(),
            Assessment.status     == "Active",
        ).all()
        return [
            {
                "id":          a.id,
                "title":       a.title,
                "description": a.description or "",
                "group":       a.group_name or "",
                "status":      a.status or "Active",
            }
            for a in rows
        ]
    finally:
        db.close()

@app.get("/assessments/{aid}")
def get_assessment(aid: int):
    """Public — students load their exam here."""
    db = SessionLocal()
    try:
        a = db.query(Assessment).filter(Assessment.id == aid).first()
        if not a:
            raise HTTPException(status_code=404, detail="Assessment not found")

        ids     = safe_loads(a.question_ids, "[]")
        qs      = db.query(Question).filter(Question.id.in_(ids)).all()
        q_map   = {q.id: q for q in qs}
        ordered = [q_map[i] for i in ids if i in q_map]

        return {
            "id":          a.id,
            "title":       a.title,
            "description": a.description or "",
            "group":       a.group_name or "",
            "status":      a.status or "Draft",
            "questions":   [
                {
                    "id":         q.id,
                    "text":       q.text,
                    "type":       q.type,
                    "options":    safe_loads(q.options, "[]"),
                    "category":   q.category,
                    "difficulty": q.difficulty,
                }
                for q in ordered
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# ─────────────────────────────────────────────
# Submit
# ─────────────────────────────────────────────

@app.post("/submit")
def submit(s: SubmissionIn):
    db = SessionLocal()
    try:
        assessment = db.query(Assessment).filter(Assessment.id == s.assessment_id).first()
        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found")

        q_ids     = safe_loads(assessment.question_ids, "[]")
        questions = db.query(Question).filter(Question.id.in_(q_ids)).all()

        auto_score = 0
        auto_total = 0

        for q in questions:
            if q.type == "essay":
                continue

            auto_total += 1
            student_ans = s.answers.get(str(q.id), "")

            if q.type == "mcq":
                if str(student_ans).strip().upper()[:1] == str(q.correct or "").strip().upper()[:1]:
                    auto_score += 1

            elif q.type == "true_false":
                if str(student_ans).strip().lower() == str(q.correct or "").strip().lower():
                    auto_score += 1

            elif q.type in ("fill_blank", "math"):
                if normalize(student_ans) == normalize(q.correct):
                    auto_score += 1

            elif q.type == "match":
                try:
                    opts  = safe_loads(q.options, "[]")
                    given = json.loads(student_ans) if isinstance(student_ans, str) else student_ans
                    if all(str(given.get(p["left"])) == str(p["right"]) for p in opts):
                        auto_score += 1
                except Exception:
                    pass

            elif q.type == "drag_order":
                try:
                    opts  = safe_loads(q.options, "[]")
                    given = json.loads(student_ans) if isinstance(student_ans, str) else student_ans
                    if given == opts:
                        auto_score += 1
                except Exception:
                    pass

        percentage = round((auto_score / auto_total * 100) if auto_total > 0 else 0, 1)

        sub = Submission(
            candidate=s.candidate,
            email=s.email,
            assessment_id=s.assessment_id,
            answers=json.dumps(s.answers),
            total_score=auto_score,
            total_possible=auto_total,
            percentage=percentage,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)

        return {
            "submission_id":  sub.id,
            "score":          auto_score,
            "total_possible": auto_total,
            "percentage":     percentage,
            "mcq_score":      auto_score,   # kept for frontend compatibility
            "mcq_total":      auto_total,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# ─────────────────────────────────────────────
# Results (admin only)
# ─────────────────────────────────────────────

@app.get("/results")
def get_results(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    try:
        subs = db.query(Submission).order_by(Submission.submitted_at.desc()).all()
        results = []
        for s in subs:
            a = db.query(Assessment).filter(Assessment.id == s.assessment_id).first()
            results.append({
                "id":               s.id,
                "candidate":        s.candidate,
                "email":            s.email,
                "assessment_id":    s.assessment_id,
                "assessment_title": a.title if a else "Unknown",
                "submitted_at":     str(s.submitted_at),
                "total_score":      s.total_score    or 0,
                "total_possible":   s.total_possible or 0,
                "percentage":       s.percentage     or 0,
            })
        return results
    finally:
        db.close()