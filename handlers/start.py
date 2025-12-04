from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from states import OnboardingStates
from database import get_or_create_user, update_user_reminder_time
import re

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user = await get_or_create_user(message.from_user.id)
    
    # Проверяем, новый ли это пользователь (по created_at и updated_at)
    is_new_user = user.created_at == user.updated_at
    
    if is_new_user:
        # Онбординг для нового пользователя
        await message.answer(
            "Привет! Я бот-пятибук 🌿\n\n"
            "Каждый день буду задавать тебе один и тот же вопрос в одну и ту же дату, "
            "чтобы ты могла смотреть, как меняешься из года в год.\n\n"
            "Для начала, давай настроим время ежедневного напоминания.\n"
            "В какое время тебе удобно отвечать на вопросы?\n\n"
            "Отправь время в формате <b>ЧЧ:ММ</b> (например, 09:00 или 21:30)",
            parse_mode="HTML"
        )
        await state.set_state(OnboardingStates.waiting_for_time)
    else:
        # Пользователь уже зарегистрирован
        await message.answer(
            f"С возвращением! 💚\n\n"
            f"Твоё текущее время напоминаний: <b>{user.reminder_time}</b>\n\n"
            f"Доступные команды:\n"
            f"/today - сегодняшняя запись\n"
            f"/settings - изменить время напоминаний\n"
            f"/help - помощь",
            parse_mode="HTML"
        )


@router.message(OnboardingStates.waiting_for_time)
async def process_reminder_time(message: Message, state: FSMContext):
    """Обработка времени напоминания при онбординге"""
    time_text = message.text.strip()
    
    # Валидация формата HH:MM
    time_pattern = re.compile(r'^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$')
    match = time_pattern.match(time_text)
    
    if not match:
        await message.answer(
            "Неправильный формат времени ❌\n\n"
            "Пожалуйста, введи время в формате <b>ЧЧ:ММ</b>\n"
            "Например: 09:00 или 21:30",
            parse_mode="HTML"
        )
        return
    
    # Нормализуем формат (добавляем ведущий ноль если нужно)
    hours, minutes = match.groups()
    normalized_time = f"{int(hours):02d}:{int(minutes):02d}"
    
    # Сохраняем время
    success = await update_user_reminder_time(message.from_user.id, normalized_time)
    
    if success:
        await message.answer(
            f"Отлично! ✅\n\n"
            f"Время напоминаний установлено: <b>{normalized_time}</b>\n\n"
            f"Каждый день в это время я буду присылать тебе вопрос дня.\n\n"
            f"<b>Полезные команды:</b>\n"
            f"/today - сегодняшняя запись\n"
            f"/settings - изменить время напоминаний\n"
            f"/help - помощь\n\n"
            f"Можешь попробовать команду /today прямо сейчас! 🌟",
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer(
            "Произошла ошибка при сохранении времени. Попробуй ещё раз или напиши /start"
        )