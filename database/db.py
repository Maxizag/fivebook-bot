from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from database.models import Base, User, Question, Answer
from typing import Optional
from datetime import datetime
import config


# Create async engine
engine = create_async_engine(config.DATABASE_URL, echo=False)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(telegram_id: int) -> User:
    """Get existing user or create new one"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                timezone=config.DEFAULT_TIMEZONE,
                reminder_time=config.DEFAULT_REMINDER_TIME
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        
        return user


async def update_user_reminder_time(telegram_id: int, reminder_time: str) -> bool:
    """Update user's reminder time"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.reminder_time = reminder_time
            user.updated_at = datetime.utcnow()
            await session.commit()
            return True
        return False


async def get_question_for_date(user_id: int, date_key: str) -> Optional[Question]:
    """Get question for specific date (MM-DD format)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Question).where(
                Question.user_id == user_id,
                Question.date_key == date_key
            )
        )
        return result.scalar_one_or_none()


async def create_question(user_id: int, date_key: str, question_text: str) -> Question:
    """Create new question for a date"""
    async with AsyncSessionLocal() as session:
        question = Question(
            user_id=user_id,
            date_key=date_key,
            question_text=question_text
        )
        session.add(question)
        await session.commit()
        await session.refresh(question)
        return question


async def get_answers_for_question(question_id: int) -> list[Answer]:
    """Get all answers for a question, ordered by year"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer)
            .where(Answer.question_id == question_id)
            .order_by(Answer.year.asc())
        )
        return list(result.scalars().all())


async def get_answer_for_year(user_id: int, question_id: int, year: int) -> Optional[Answer]:
    """Check if answer exists for specific year"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(
                Answer.user_id == user_id,
                Answer.question_id == question_id,
                Answer.year == year
            )
        )
        return result.scalar_one_or_none()


async def create_answer(user_id: int, question_id: int, answer_text: str, answer_date: str, year: int) -> Answer:
    """Create new answer"""
    async with AsyncSessionLocal() as session:
        answer = Answer(
            user_id=user_id,
            question_id=question_id,
            answer_text=answer_text,
            answer_date=answer_date,
            year=year
        )
        session.add(answer)
        await session.commit()
        await session.refresh(answer)
        return answer


async def get_all_users() -> list[User]:
    """Get all users (for scheduler)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        return list(result.scalars().all())
    
async def update_answer_text(answer_id: int, new_text: str) -> bool:
    """Update answer text"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        answer = result.scalar_one_or_none()
        
        if answer:
            answer.answer_text = new_text
            answer.updated_at = datetime.utcnow()
            await session.commit()
            return True
        return False


async def update_answer_year(answer_id: int, new_year: int, date_key: str) -> bool:
    """Update answer year"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        answer = result.scalar_one_or_none()
        
        if answer:
            answer.year = new_year
            answer.answer_date = f"{new_year}-{date_key}"
            answer.updated_at = datetime.utcnow()
            await session.commit()
            return True
        return False


async def delete_answer(answer_id: int) -> bool:
    """Delete answer"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        answer = result.scalar_one_or_none()
        
        if answer:
            await session.delete(answer)
            await session.commit()
            return True
        return False


async def get_answer_by_id(answer_id: int) -> Optional[Answer]:
    """Get answer by ID"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        return result.scalar_one_or_none()