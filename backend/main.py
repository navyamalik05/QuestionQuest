from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any
from database import SessionLocal, Question, Assessment, Submission
import json
import os
from dotenv import load_dotenv

load_dotenv()

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
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")

    return {"success": True, "message": "Admin login successful"}


# ─────────────────────────────────────────────
# Questions
# ─────────────────────────────────────────────

@app.get("/questions")
def get_questions():
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
def create_question(q: QuestionIn):
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
def delete_question(qid: int):
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
def list_assessments():
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
def create_assessment(a: AssessmentIn):
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


@app.get("/assessments/{aid}")
def get_assessment(aid: int):
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
def update_assessment(aid: int, data: AssessmentUpdate):
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
def delete_assessment(aid: int):
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
def get_results():
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