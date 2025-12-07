import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database import init_db
from handlers import start, daily, commands, settings, date_view, evening_reminder
from scheduler import ReminderScheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    # Проверка токена
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    # Проверка состояния базы данных
    logger.info("Checking database...")
    logger.info("Database ready. Use 'alembic upgrade head' to apply migrations if needed.")
    
    # Создание бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрация роутеров (порядок важен!)
    dp.include_router(start.router)
    dp.include_router(settings.router)
    dp.include_router(commands.router)
    dp.include_router(date_view.router)
    dp.include_router(evening_reminder.router)
    dp.include_router(daily.router)
    
    # Запуск планировщика напоминаний
    logger.info("Starting reminder scheduler...")
    reminder_scheduler = ReminderScheduler(bot)
    reminder_scheduler.start()
    
    try:
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        reminder_scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")