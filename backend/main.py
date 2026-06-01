from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any
from database import SessionLocal, Question, Assessment, Submission
import json
import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Justice_2026!")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5500")

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok", "message": "QuestionQuest API is running"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_ORIGIN,
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Models ──────────────────────────────────────────────────

class AdminLogin(BaseModel):
    email: str
    password: str

class QuestionIn(BaseModel):
    text: str
    type: str           # mcq | essay | fill_blank | true_false | match | drag_order | math
    options: List[Any] = []   # Any accepts strings OR objects ({left,right} etc)
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

# ── Admin Auth ───────────────────────────────────────────────────────

@app.post("/admin-login")
def admin_login(data: AdminLogin):
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return {"success": True}

# ── Questions ───────────────────────────────────────────────────────

@app.get("/questions")
def get_questions():
    db = SessionLocal()
    items = db.query(Question).all()
    return [
        {
            "id": q.id,
            "text": q.text,
            "type": q.type,
            "options": json.loads(q.options or "[]"),
            "correct": q.correct,
            "category": q.category,
            "difficulty": q.difficulty,
        }
        for q in items
    ]

@app.post("/questions")
def create_question(q: QuestionIn):
    db = SessionLocal()
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

@app.delete("/questions/{qid}")
def delete_question(qid: int):
    db = SessionLocal()
    q = db.query(Question).filter(Question.id == qid).first()
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(q)
    db.commit()
    return {"message": "Deleted"}

# ── Assessments ──────────────────────────────────────────────────────

@app.get("/assessments")
def list_assessments():
    db = SessionLocal()
    rows = db.query(Assessment).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "description": a.description if hasattr(a, "description") else "",
            "question_ids": json.loads(a.question_ids or "[]"),
            "group": a.group_name or "",
            "status": a.status or "Draft",
        }
        for a in rows
    ]

@app.post("/assessments")
def create_assessment(a: AssessmentIn):
    db = SessionLocal()
    assessment = Assessment(
        title=a.title,
        description=a.description,
        question_ids=json.dumps(a.question_ids),
        group_name=a.group,
        status=a.status,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return {"id": assessment.id, "message": "Assessment created"}

@app.get("/assessments/{aid}")
def get_assessment(aid: int):
    db = SessionLocal()
    a = db.query(Assessment).filter(Assessment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    ids = json.loads(a.question_ids or "[]")
    questions = db.query(Question).filter(Question.id.in_(ids)).all()
    q_map = {q.id: q for q in questions}
    ordered = [q_map[i] for i in ids if i in q_map]
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description if hasattr(a, "description") else "",
        "group": a.group_name or "",
        "status": a.status or "Draft",
        "questions": [
            {
                "id": q.id,
                "text": q.text,
                "type": q.type,
                "options": json.loads(q.options or "[]"),
                "category": q.category,
                "difficulty": q.difficulty,
            }
            for q in ordered
        ],
    }

@app.put("/assessments/{aid}")
def update_assessment(aid: int, data: AssessmentUpdate):
    db = SessionLocal()
    a = db.query(Assessment).filter(Assessment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    if data.title is not None:       a.title = data.title
    if data.description is not None: a.description = data.description
    if data.question_ids is not None: a.question_ids = json.dumps(data.question_ids)
    if data.group is not None:       a.group_name = data.group
    if data.status is not None:      a.status = data.status
    db.commit()
    return {"message": "Updated"}

@app.delete("/assessments/{aid}")
def delete_assessment(aid: int):
    db = SessionLocal()
    a = db.query(Assessment).filter(Assessment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(a)
    db.commit()
    return {"message": "Deleted"}

@app.get("/assessments/by-group/{group_name}")
def get_assessments_for_group(group_name: str):
    db = SessionLocal()
    rows = db.query(Assessment).filter(
        Assessment.group_name == group_name,
        Assessment.status == "Active"
    ).all()
    return [
        {"id": a.id, "title": a.title,
         "description": a.description if hasattr(a, "description") else ""}
        for a in rows
    ]

# ── Submit ───────────────────────────────────────────────────────────

@app.post("/submit")
def submit(s: SubmissionIn):
    db = SessionLocal()
    assessment = db.query(Assessment).filter(Assessment.id == s.assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    q_ids = json.loads(assessment.question_ids or "[]")
    questions = db.query(Question).filter(Question.id.in_(q_ids)).all()

    auto_score = 0
    auto_total = 0

    for q in questions:
        if q.type == "essay":
            continue  # essays are graded manually — not counted in auto_total

        auto_total += 1

        if q.type == "mcq":
            given  = s.answers.get(str(q.id), "").strip().upper()
            stored = (q.correct or "").strip().upper()
            if given[:1] == stored[:1]:
                auto_score += 1

        elif q.type == "true_false":
            given  = s.answers.get(str(q.id), "").strip().lower()
            stored = (q.correct or "").strip().lower()
            if given == stored:
                auto_score += 1

        elif q.type in ("fill_blank", "math"):
            # Normalize: strip, lowercase, collapse spaces
            given  = s.answers.get(str(q.id), "").strip().lower().replace(" ", "")
            stored = (q.correct or "").strip().lower().replace(" ", "")
            if given == stored:
                auto_score += 1

        elif q.type == "match":
            # options = [{left, right}, ...]
            # student answer = JSON string {"left_val": "right_val", ...}
            try:
                opts      = json.loads(q.options or "[]")
                given_raw = s.answers.get(str(q.id), "{}")
                given     = json.loads(given_raw) if isinstance(given_raw, str) else given_raw
                if all(str(given.get(p["left"])) == str(p["right"]) for p in opts):
                    auto_score += 1
            except Exception:
                pass

        elif q.type == "drag_order":
            # options = ["item1","item2",...] in CORRECT order
            # student answer = JSON string of reordered array
            try:
                opts      = json.loads(q.options or "[]")
                given_raw = s.answers.get(str(q.id), "[]")
                given     = json.loads(given_raw) if isinstance(given_raw, str) else given_raw
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
        "submission_id": sub.id,
        "score": auto_score,
        "total_possible": auto_total,
        "percentage": percentage,

        # Keeping these old names too so your current frontend does not break
        "mcq_score": auto_score,
        "mcq_total": auto_total,
    }

# ── Results ─────────────────────────────────────────────────────────

@app.get("/results")
def get_results():
    db = SessionLocal()
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