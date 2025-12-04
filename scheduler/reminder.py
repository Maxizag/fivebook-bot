import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from database import get_all_users
from aiogram import Bot
import logging

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=pytz.UTC)
        
    async def send_daily_reminder(self, user_telegram_id: int):
        """Отправить ежедневное напоминание пользователю"""
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from aiogram.fsm.context import FSMContext
            from aiogram.fsm.storage.base import StorageKey
            from handlers.daily import show_daily_question
            
            # Создаём "фейковое" сообщение для использования show_daily_question
            # В реальности отправим просто текстовое сообщение
            from database import get_or_create_user, get_question_for_date, get_answer_for_year
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            from utils import is_leap_year
        
            now = datetime.now()
            date_key = now.strftime("%m-%d")
            current_year = now.year
            
            # Если сегоднnowя 29 февраля в невисокосный год - не отправляем напоминание
            if date_key == "02-29" and not is_leap_year(current_year):
                logger.info(f"Skipping reminder for user {user_telegram_id} - Feb 29 in non-leap year")
                return
            
            user = await get_or_create_user(user_telegram_id)
            
            now = datetime.now()
            date_key = now.strftime("%m-%d")
            current_year = now.year
            
            # Проверяем, есть ли вопрос для этой даты
            question = await get_question_for_date(user.id, date_key)
            
            if question is None:
                # Сценарий A: Первый год, вопрос не создан
                await self.bot.send_message(
                    user_telegram_id,
                    "Привет! Время для записи в пятибук 🌿\n\n"
                    "Сегодня у тебя ещё нет вопроса для этого дня.\n\n"
                    "Используй команду /today чтобы создать вопрос и ответить на него."
                )
            else:
                # Сценарий B: Вопрос уже существует
                # Проверяем, есть ли уже ответ за текущий год
                existing_answer = await get_answer_for_year(user.id, question.id, current_year)
                
                if existing_answer:
                    # Ответ уже есть
                    await self.bot.send_message(
                        user_telegram_id,
                        f"Доброе утро! ☀️\n\n"
                        f"Сегодняшний вопрос:\n"
                        f"<b>{question.question_text}</b>\n\n"
                        f"Ты уже ответила на этот вопрос в {current_year} году ✅",
                        parse_mode="HTML"
                    )
                else:
                    # Показываем вопрос и кнопки
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="📖 Посмотреть прошлые ответы",
                            callback_data="show_past_answers"
                        )],
                        [InlineKeyboardButton(
                            text=f"✍️ Написать ответ за {current_year}",
                            callback_data="write_answer"
                        )]
                    ])
                    
                    # Для удобства также предлагаем /today
                    await self.bot.send_message(
                        user_telegram_id,
                        f"Доброе утро! ☀️\n\n"
                        f"Сегодняшний вопрос для тебя:\n\n"
                        f"<b>{question.question_text}</b>\n\n"
                        f"Используй команду /today чтобы ответить на вопрос.",
                        parse_mode="HTML"
                    )
            
            logger.info(f"Reminder sent to user {user_telegram_id}")
            
        except Exception as e:
            logger.error(f"Error sending reminder to user {user_telegram_id}: {e}")
    
    async def check_reminders(self):
        """Проверить, кому нужно отправить напоминания"""
        try:
            users = await get_all_users()
            now = datetime.now()
            
            for user in users:
                try:
                    # Парсим время напоминания
                    reminder_hour, reminder_minute = map(int, user.reminder_time.split(':'))
                    
                    # Получаем текущее время в часовом поясе пользователя
                    user_tz = pytz.timezone(user.timezone)
                    user_now = datetime.now(user_tz)
                    
                    # Проверяем, совпадает ли время
                    if user_now.hour == reminder_hour and user_now.minute == reminder_minute:
                        await self.send_daily_reminder(user.telegram_id)
                        
                except Exception as e:
                    logger.error(f"Error processing user {user.telegram_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in check_reminders: {e}")
    
    def start(self):
        """Запустить планировщик"""
        # Проверяем каждую минуту
        self.scheduler.add_job(
            self.check_reminders,
            trigger=CronTrigger(minute='*'),
            id='check_reminders',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Reminder scheduler started")
    
    def shutdown(self):
        """Остановить планировщик"""
        self.scheduler.shutdown()
        logger.info("Reminder scheduler stopped")