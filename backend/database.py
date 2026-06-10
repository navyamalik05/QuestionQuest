import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exam.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

class Question(Base):
    __tablename__ = "questions"
    id         = Column(Integer, primary_key=True)
    text       = Column(Text)
    type       = Column(String)        # "mcq" or "text"
    options    = Column(Text)          # JSON list of answer strings
    correct    = Column(String)        # correct answer letter e.g. "A"
    category   = Column(String)
    difficulty = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    media = Column(Text, default="[]")
    interaction_config = Column(Text, default="")


class ItemSet(Base):
    __tablename__ = "item_sets"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    stimulus_text = Column(Text, default="")
    stimulus_media = Column(Text, default="[]")
    category = Column(String, default="")
    difficulty = Column(String, default="Intermediate")
    created_at = Column(DateTime, default=datetime.utcnow)


class ItemSubQuestion(Base):
    __tablename__ = "item_subquestions"

    id = Column(Integer, primary_key=True)
    item_set_id = Column(Integer, nullable=False)
    text = Column(Text, default="")
    type = Column(String, nullable=False)
    options = Column(Text, default="[]")
    correct = Column(Text, default="")
    interaction_config = Column(Text, default="")
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Assessment(Base):
    __tablename__ = "assessments"
    id           = Column(Integer, primary_key=True)
    title        = Column(String)
    description  = Column(Text, default="")
    question_ids = Column(Text)        # JSON list of Question IDs
    group_name   = Column(String, default="")
    status       = Column(String, default="Draft")   # "Draft" | "Active"
    assessment_items = Column(Text, default="[]")

class Submission(Base):
    __tablename__ = "submissions"
    id             = Column(Integer, primary_key=True)
    candidate      = Column(String)
    email          = Column(String)
    assessment_id  = Column(Integer)
    answers        = Column(Text)
    ai_scores      = Column(Text)
    total_score    = Column(Integer)
    total_possible = Column(Integer, default=0)
    percentage     = Column(Integer, default=0)
    submitted_at   = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)