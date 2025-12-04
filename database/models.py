from datetime import datetime
from sqlalchemy import BigInteger, String, Text, Integer, DateTime, UniqueConstraint, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import List


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Ho_Chi_Minh")
    reminder_time: Mapped[str] = mapped_column(String(5), default="09:00")
    language: Mapped[str] = mapped_column(String(10), default="ru", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    questions: Mapped[List["Question"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    answers: Mapped[List["Answer"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, timezone={self.timezone})>"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    date_key: Mapped[str] = mapped_column(String(5), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="questions")
    answers: Mapped[List["Answer"]] = relationship(back_populates="question", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('user_id', 'date_key', name='uq_user_date'),
    )

    def __repr__(self):
        return f"<Question(date_key={self.date_key}, text={self.question_text[:30]}...)>"


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_date: Mapped[str] = mapped_column(String(10), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint('user_id', 'question_id', 'year', name='uq_user_question_year'),
    )

    def __repr__(self):
        return f"<Answer(year={self.year}, text={self.answer_text[:30]}...)>"