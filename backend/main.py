from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any
from database import SessionLocal, Question, Assessment, Submission, AdminUser
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dotenv import load_dotenv
from passlib.context import CryptContext
from jose import jwt, JWTError

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12

ADMIN_BOOTSTRAP_NAME = os.getenv("ADMIN_BOOTSTRAP_NAME", "")
ADMIN_BOOTSTRAP_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "")
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─────────────────────────────────────────────
# Environment Config
# ─────────────────────────────────────────────

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Justice_2026!")

# Your deployed frontend/domain URLs
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://assessmentjustice.org")
FRONTEND_ORIGIN_WWW = os.getenv("FRONTEND_ORIGIN_WWW", "https://www.assessmentjustice.org")
VERCEL_ORIGIN = os.getenv("VERCEL_ORIGIN", "")

# ─────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────

app = FastAPI(
    title="QuestionQuest API",
    version="1.0.0"
)

@app.on_event("startup")
def create_initial_admin():
    db = SessionLocal()

    try:
        existing_count = db.query(AdminUser).count()

        if existing_count == 0:
            if not ADMIN_BOOTSTRAP_EMAIL or not ADMIN_BOOTSTRAP_PASSWORD:
                print("No bootstrap admin created. Missing ADMIN_BOOTSTRAP_EMAIL or ADMIN_BOOTSTRAP_PASSWORD.")
                return

            admin = AdminUser(
                name=ADMIN_BOOTSTRAP_NAME or "Initial Admin",
                email=ADMIN_BOOTSTRAP_EMAIL.lower().strip(),
                password_hash=hash_password(ADMIN_BOOTSTRAP_PASSWORD),
                is_active=True
            )

            db.add(admin)
            db.commit()
            print(f"Bootstrap admin created: {admin.email}")

    finally:
        db.close()

# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────
# This allows:
# - local frontend testing
# - your GoDaddy custom domain
# - your Vercel deployment URL if provided
# - Vercel preview deployments through regex

allowed_origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://assessmentjustice.org",
    "https://www.assessmentjustice.org",
    FRONTEND_ORIGIN,
    FRONTEND_ORIGIN_WWW,
]

if VERCEL_ORIGIN:
    allowed_origins.append(VERCEL_ORIGIN)

# Remove duplicates and empty strings
allowed_origins = list(set([origin for origin in allowed_origins if origin]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Health Checks
# ─────────────────────────────────────────────

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "QuestionQuest API is running",
        "allowed_origins": allowed_origins
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class AdminLogin(BaseModel):
    name: str = ""
    email: str
    password: str


class QuestionIn(BaseModel):
    text: str
    type: str
    options: List[Any] = []
    correct: str = ""
    category: str = ""
    difficulty: str = "Intermediate"


class AssessmentIn(BaseModel):
    title: str
    description: str = ""
    question_ids: List[int] = []
    group: str = ""
    status: str = "Draft"


class AssessmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    question_ids: Optional[List[int]] = None
    group: Optional[str] = None
    status: Optional[str] = None


class SubmissionIn(BaseModel):
    candidate: str
    email: str
    assessment_id: int
    answers: dict


class AdminUserIn(BaseModel):
    name: str
    email: str
    password: str


def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str):
    return pwd_context.verify(password, password_hash)

def create_admin_token(admin: AdminUser):
    payload = {
        "sub": str(admin.id),
        "email": admin.email,
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def require_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")

    token = authorization.replace("Bearer ", "").strip()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        admin_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid admin token")

    db = SessionLocal()
    admin = db.query(AdminUser).filter(
        AdminUser.id == admin_id,
        AdminUser.is_active == True
    ).first()

    if not admin:
        raise HTTPException(status_code=401, detail="Admin user not found or inactive")

    return admin

# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def safe_json_loads(value, fallback):
    try:
        return json.loads(value or fallback)
    except Exception:
        return json.loads(fallback)


def normalize_answer(value):
    return str(value or "").strip().lower().replace(" ", "")


# ─────────────────────────────────────────────
# Admin Auth
# ─────────────────────────────────────────────

@app.post("/admin-login")
def admin_login(data: AdminLogin):
    db = SessionLocal()

    admin = db.query(AdminUser).filter(
        AdminUser.email == data.email.lower().strip(),
        AdminUser.is_active == True
    ).first()

    if not admin:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    if not verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    token = create_admin_token(admin)

    return {
        "success": True,
        "token": token,
        "admin": {
            "id": admin.id,
            "name": admin.name,
            "email": admin.email
        }
    }

# ─────────────────────────────────────────────
# Questions
# ─────────────────────────────────────────────

@app.get("/questions")
def get_questions(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    try:
        items = db.query(Question).all()

        return [
            {
                "id": q.id,
                "text": q.text,
                "type": q.type,
                "options": safe_json_loads(q.options, "[]"),
                "correct": q.correct,
                "category": q.category,
                "difficulty": q.difficulty,
            }
            for q in items
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

        return {
            "id": item.id,
            "message": "Question created"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create question: {str(e)}")

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

        return {"message": "Question deleted"}

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete question: {str(e)}")

    finally:
        db.close()


# ─────────────────────────────────────────────
# Assessments
# ─────────────────────────────────────────────

@app.get("/assessments")
def list_assessments(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    try:
        rows = db.query(Assessment).all()

        return [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description or "",
                "question_ids": safe_json_loads(a.question_ids, "[]"),
                "group": a.group_name or "",
                "status": a.status or "Draft",
            }
            for a in rows
        ]

    finally:
        db.close()


@app.post("/assessments")
def create_assessment(a: AssessmentIn, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    try:
        if not a.title.strip():
            raise HTTPException(status_code=400, detail="Assessment title is required")

        assessment = Assessment(
            title=a.title.strip(),
            description=a.description.strip(),
            question_ids=json.dumps(a.question_ids),
            group_name=a.group.strip(),
            status=a.status.strip() or "Draft",
        )

        db.add(assessment)
        db.commit()
        db.refresh(assessment)

        return {
            "id": assessment.id,
            "message": "Assessment created"
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create assessment: {str(e)}")

    finally:
        db.close()

@app.post("/assessments")
def create_assessment(a: AssessmentIn, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    try:
        a = db.query(Assessment).filter(Assessment.id == aid).first()

        if not a:
            raise HTTPException(status_code=404, detail="Assessment not found")

        ids = safe_json_loads(a.question_ids, "[]")

        if not ids:
            ordered_questions = []
        else:
            questions = db.query(Question).filter(Question.id.in_(ids)).all()
            q_map = {q.id: q for q in questions}
            ordered_questions = [q_map[i] for i in ids if i in q_map]

        return {
            "id": a.id,
            "title": a.title,
            "description": a.description or "",
            "group": a.group_name or "",
            "status": a.status or "Draft",
            "questions": [
                {
                    "id": q.id,
                    "text": q.text,
                    "type": q.type,
                    "options": safe_json_loads(q.options, "[]"),
                    "category": q.category,
                    "difficulty": q.difficulty,
                }
                for q in ordered_questions
            ],
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load assessment: {str(e)}")

    finally:
        db.close()


@app.put("/assessments/{aid}")
def update_assessment(aid: int, data: AssessmentUpdate, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    try:
        a = db.query(Assessment).filter(Assessment.id == aid).first()

        if not a:
            raise HTTPException(status_code=404, detail="Assessment not found")

        if data.title is not None:
            a.title = data.title.strip()

        if data.description is not None:
            a.description = data.description.strip()

        if data.question_ids is not None:
            a.question_ids = json.dumps(data.question_ids)

        if data.group is not None:
            a.group_name = data.group.strip()

        if data.status is not None:
            a.status = data.status.strip()

        db.commit()

        return {"message": "Assessment updated"}

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update assessment: {str(e)}")

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

        return {"message": "Assessment deleted"}

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete assessment: {str(e)}")

    finally:
        db.close()


@app.get("/assessments/by-group/{group_name}")
def get_assessments_for_group(group_name: str):
    db = SessionLocal()

    try:
        clean_group = group_name.strip()

        rows = db.query(Assessment).filter(
            Assessment.group_name == clean_group,
            Assessment.status == "Active"
        ).all()

        return [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description or "",
                "group": a.group_name or "",
                "status": a.status or "Draft",
            }
            for a in rows
        ]

    finally:
        db.close()


# ─────────────────────────────────────────────
# Submit Assessment
# ─────────────────────────────────────────────

@app.post("/submit")
def submit(s: SubmissionIn):
    db = SessionLocal()

    try:
        assessment = db.query(Assessment).filter(Assessment.id == s.assessment_id).first()

        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found")

        q_ids = safe_json_loads(assessment.question_ids, "[]")

        if not q_ids:
            raise HTTPException(status_code=400, detail="Assessment has no questions")

        questions = db.query(Question).filter(Question.id.in_(q_ids)).all()

        auto_score = 0
        auto_total = 0

        for q in questions:
            if q.type == "essay":
                continue

            auto_total += 1

            student_answer = s.answers.get(str(q.id), "")

            if q.type == "mcq":
                given = str(student_answer or "").strip().upper()
                stored = str(q.correct or "").strip().upper()

                if given[:1] == stored[:1]:
                    auto_score += 1

            elif q.type == "true_false":
                given = str(student_answer or "").strip().lower()
                stored = str(q.correct or "").strip().lower()

                if given == stored:
                    auto_score += 1

            elif q.type in ("fill_blank", "math"):
                given = normalize_answer(student_answer)
                stored = normalize_answer(q.correct)

                if given == stored:
                    auto_score += 1

            elif q.type == "match":
                try:
                    opts = safe_json_loads(q.options, "[]")

                    given_raw = student_answer
                    given = json.loads(given_raw) if isinstance(given_raw, str) else given_raw

                    if all(str(given.get(p["left"])) == str(p["right"]) for p in opts):
                        auto_score += 1

                except Exception:
                    pass

            elif q.type == "drag_order":
                try:
                    opts = safe_json_loads(q.options, "[]")

                    given_raw = student_answer
                    given = json.loads(given_raw) if isinstance(given_raw, str) else given_raw

                    if given == opts:
                        auto_score += 1

                except Exception:
                    pass

        percentage = round((auto_score / auto_total * 100) if auto_total > 0 else 0, 1)

        # This assumes your Submission model has:
        # total_possible and percentage columns.
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
            "submission_id": sub.id,
            "score": auto_score,
            "total_possible": auto_total,
            "percentage": percentage,

            # Old names kept so your current frontend does not break
            "mcq_score": auto_score,
            "mcq_total": auto_total,
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit assessment: {str(e)}")

    finally:
        db.close()


# ─────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────

@app.get("/results")
def get_results(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    try:
        subs = db.query(Submission).order_by(Submission.submitted_at.desc()).all()

        results = []

        for s in subs:
            assessment = db.query(Assessment).filter(Assessment.id == s.assessment_id).first()

            total_possible = getattr(s, "total_possible", 0) or 0
            percentage = getattr(s, "percentage", 0) or 0

            results.append({
                "id": s.id,
                "candidate": s.candidate,
                "email": s.email,
                "assessment_id": s.assessment_id,
                "assessment_title": assessment.title if assessment else "Unknown Assessment",
                "submitted_at": str(s.submitted_at),
                "total_score": s.total_score or 0,
                "total_possible": total_possible,
                "percentage": percentage,
            })

        return results

    finally:
        db.close()


@app.get("/admin-users")
def list_admin_users(current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()
    admins = db.query(AdminUser).order_by(AdminUser.created_at.desc()).all()

    return [
        {
            "id": a.id,
            "name": a.name,
            "email": a.email,
            "is_active": a.is_active,
            "created_at": str(a.created_at)
        }
        for a in admins
    ]

@app.post("/admin-users")
def create_admin_user(data: AdminUserIn, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    existing = db.query(AdminUser).filter(
        AdminUser.email == data.email.lower().strip()
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Admin email already exists")

    admin = AdminUser(
        name=data.name.strip(),
        email=data.email.lower().strip(),
        password_hash=hash_password(data.password),
        is_active=True
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    return {
        "id": admin.id,
        "name": admin.name,
        "email": admin.email,
        "is_active": admin.is_active,
        "message": "Admin user created"
    }

@app.delete("/admin-users/{admin_id}")
def deactivate_admin_user(admin_id: int, current_admin: AdminUser = Depends(require_admin)):
    db = SessionLocal()

    if current_admin.id == admin_id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()

    if not admin:
        raise HTTPException(status_code=404, detail="Admin user not found")

    admin.is_active = False
    db.commit()

    return {"message": "Admin user deactivated"}