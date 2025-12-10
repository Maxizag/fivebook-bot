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

            # Если сегодня 29 февраля в невисокосный год - не отправляем напоминание
            if date_key == "02-29" and not is_leap_year(current_year):
                logger.info(f"Skipping reminder for user {user_telegram_id} - Feb 29 in non-leap year")
                return

            user = await get_or_create_user(user_telegram_id)
            
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

    async def send_evening_reminder(self, user_telegram_id: int):
        """Отправить вечернее напоминание в 23:00, если за сегодня нет записи"""
        try:
            from database import get_or_create_user, get_question_for_date, get_answer_for_year
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            user = await get_or_create_user(user_telegram_id)

            now = datetime.now()
            date_key = now.strftime("%m-%d")
            current_year = now.year

            # Проверяем, есть ли вопрос для этой даты
            question = await get_question_for_date(user.id, date_key)

            # Проверяем, есть ли ответ за сегодняшний год
            has_answer = False
            if question:
                existing_answer = await get_answer_for_year(user.id, question.id, current_year)
                has_answer = existing_answer is not None

            # Если ответ уже есть - ничего не отправляем
            if has_answer:
                logger.info(f"Skipping evening reminder for user {user_telegram_id} - answer already exists")
                return

            # Вариант 1: Вопрос есть, но нет ответа
            if question:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✍️ Ответить за сегодня",
                        callback_data="evening_answer_today"
                    )],
                    [InlineKeyboardButton(
                        text="🙈 Пропустить",
                        callback_data="evening_skip"
                    )]
                ])

                await self.bot.send_message(
                    user_telegram_id,
                    f"🌙 Уже 23:00, а ответа за сегодня ещё нет.\n\n"
                    f"Сегодняшний вопрос:\n"
                    f"<b>{question.question_text}</b>\n\n"
                    f"Хочешь записать ответ сейчас?",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                # Вариант 2: Вопроса для этой даты ещё нет
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✍️ Добавить вопрос и ответ",
                        callback_data="evening_add_question"
                    )],
                    [InlineKeyboardButton(
                        text="🙈 Пропустить",
                        callback_data="evening_skip"
                    )]
                ])

                await self.bot.send_message(
                    user_telegram_id,
                    "🌙 Уже 23:00, а записи за сегодня ещё нет.\n\n"
                    "Хочешь добавить вопрос и ответ за сегодняшний день?",
                    reply_markup=keyboard
                )

            logger.info(f"Evening reminder sent to user {user_telegram_id}")

        except Exception as e:
            logger.error(f"Error sending evening reminder to user {user_telegram_id}: {e}")

    async def check_evening_reminders(self):
        """Проверить, кому нужно отправить вечерние напоминания в 23:00"""
        try:
            users = await get_all_users()

            for user in users:
                try:
                    # Получаем текущее время в часовом поясе пользователя
                    user_tz = pytz.timezone(user.timezone)
                    user_now = datetime.now(user_tz)

                    # Парсим основное время напоминания
                    reminder_hour, reminder_minute = map(int, user.reminder_time.split(':'))

                    # Проверяем, что сейчас 23:00 по локальному времени пользователя
                    # И что основное напоминание не установлено на 23:00 (чтобы не дублировать)
                    if user_now.hour == 23 and user_now.minute == 0:
                        # Если основное напоминание на 23:00, отправляем вечернее в 22:30
                        if reminder_hour == 23 and reminder_minute == 0:
                            # Пропускаем, чтобы не дублировать
                            logger.info(f"Skipping evening reminder for user {user.telegram_id} - main reminder is at 23:00")
                            continue

                        await self.send_evening_reminder(user.telegram_id)

                    # Альтернативный вариант: если основное напоминание на 23:00, отправляем вечернее в 22:30
                    elif user_now.hour == 22 and user_now.minute == 30:
                        if reminder_hour == 23 and reminder_minute == 0:
                            await self.send_evening_reminder(user.telegram_id)

                except Exception as e:
                    logger.error(f"Error processing evening reminder for user {user.telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Error in check_evening_reminders: {e}")

    async def send_morning_yesterday_reminder(self, user_telegram_id: int):
        """Отправить утреннее напоминание в 09:00 про пропущенный вчерашний день"""
        try:
            from database import get_or_create_user, get_question_for_date, get_answer_for_year
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            user = await get_or_create_user(user_telegram_id)

            # Получаем вчерашнюю дату
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            yesterday_date_key = yesterday.strftime("%m-%d")
            yesterday_year = yesterday.year

            # Проверяем, есть ли вопрос для вчерашней даты
            question = await get_question_for_date(user.id, yesterday_date_key)

            # Проверяем, есть ли ответ за вчерашний год
            has_answer = False
            if question:
                existing_answer = await get_answer_for_year(user.id, question.id, yesterday_year)
                has_answer = existing_answer is not None

            # Если ответ уже есть - ничего не отправляем
            if has_answer:
                logger.info(f"Skipping morning yesterday reminder for user {user_telegram_id} - answer already exists")
                return

            # Форматируем вчерашнюю дату для отображения (ДД.ММ)
            yesterday_label = yesterday.strftime("%d.%m")

            # Вариант 1: Вопрос есть, но нет ответа
            if question:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"✍️ Записать ответ за {yesterday_label}",
                        callback_data=f"morning_yesterday_answer:{yesterday_date_key}:{yesterday_year}"
                    )],
                    [InlineKeyboardButton(
                        text="🙈 Пропустить вчера",
                        callback_data="morning_yesterday_skip"
                    )]
                ])

                await self.bot.send_message(
                    user_telegram_id,
                    f"Доброе утро! ☀️\\n\\n"
                    f"Похоже, вчера ({yesterday_label}) ты не успела сделать запись.\\n\\n"
                    f"Вопрос дня:\\n"
                    f"<b>{question.question_text}</b>\\n\\n"
                    f"Хочешь записать ответ за вчера сейчас?",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                # Вариант 2: Вопроса для вчерашней даты ещё нет
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"✍️ Добавить вопрос и ответ за {yesterday_label}",
                        callback_data=f"morning_yesterday_add:{yesterday_date_key}:{yesterday_year}"
                    )],
                    [InlineKeyboardButton(
                        text="🙈 Пропустить вчера",
                        callback_data="morning_yesterday_skip"
                    )]
                ])

                await self.bot.send_message(
                    user_telegram_id,
                    f"Доброе утро! ☀️\\n\\n"
                    f"Похоже, вчера ({yesterday_label}) ты не успела сделать запись.\\n\\n"
                    f"Хочешь добавить вопрос и ответ за вчера сейчас?",
                    reply_markup=keyboard
                )

            logger.info(f"Morning yesterday reminder sent to user {user_telegram_id}")

        except Exception as e:
            logger.error(f"Error sending morning yesterday reminder to user {user_telegram_id}: {e}")

    async def check_morning_yesterday_reminders(self):
        """Проверить, кому нужно отправить утренние напоминания про вчерашний день в 09:00"""
        try:
            users = await get_all_users()

            for user in users:
                try:
                    # Получаем текущее время в часовом поясе пользователя
                    user_tz = pytz.timezone(user.timezone)
                    user_now = datetime.now(user_tz)

                    # Проверяем, что сейчас 09:00 по локальному времени пользователя
                    if user_now.hour == 9 and user_now.minute == 0:
                        await self.send_morning_yesterday_reminder(user.telegram_id)

                except Exception as e:
                    logger.error(f"Error processing morning yesterday reminder for user {user.telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Error in check_morning_yesterday_reminders: {e}")

    def start(self):
        """Запустить планировщик"""
        # Проверяем каждую минуту утренние напоминания
        self.scheduler.add_job(
            self.check_reminders,
            trigger=CronTrigger(minute='*'),
            id='check_reminders',
            replace_existing=True
        )

        # Проверяем каждую минуту вечерние напоминания
        self.scheduler.add_job(
            self.check_evening_reminders,
            trigger=CronTrigger(minute='*'),
            id='check_evening_reminders',
            replace_existing=True
        )

        # Проверяем каждую минуту утренние напоминания про вчерашний день
        self.scheduler.add_job(
            self.check_morning_yesterday_reminders,
            trigger=CronTrigger(minute='*'),
            id='check_morning_yesterday_reminders',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Reminder scheduler started (morning, evening, and morning yesterday)")
    
    def shutdown(self):
        """Остановить планировщик"""
        self.scheduler.shutdown()
        logger.info("Reminder scheduler stopped")