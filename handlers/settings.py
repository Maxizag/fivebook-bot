import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from states import SettingsStates
from database import get_or_create_user, update_user_reminder_time
import re

router = Router()


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    """Команда /settings - изменить настройки"""
    user = await get_or_create_user(message.from_user.id)
    
    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"Текущее время напоминаний: <b>{user.reminder_time}</b>\n\n"
        f"Чтобы изменить время, отправь новое время в формате <b>ЧЧ:ММ</b>\n"
        f"Например: 09:00 или 21:30\n\n"
        f"Или отправь /cancel для отмены",
        parse_mode="HTML"
    )
    
    await state.set_state(SettingsStates.waiting_for_new_time)


@router.message(SettingsStates.waiting_for_new_time, Command("cancel"))
async def cancel_settings(message: Message, state: FSMContext):
    """Отмена изменения настроек"""
    await message.answer("Изменение настроек отменено.")
    await state.clear()


@router.message(SettingsStates.waiting_for_new_time)
async def process_new_time(message: Message, state: FSMContext):
    """Обработка нового времени напоминания"""
    time_text = message.text.strip()
    
    # Валидация формата HH:MM
    time_pattern = re.compile(r'^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$')
    match = time_pattern.match(time_text)
    
    if not match:
        await message.answer(
            "Неправильный формат времени ❌\n\n"
            "Пожалуйста, введи время в формате <b>ЧЧ:ММ</b>\n"
            "Например: 09:00 или 21:30\n\n"
            "Или отправь /cancel для отмены",
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
            f"✅ Время напоминаний изменено!\n\n"
            f"Новое время: <b>{normalized_time}</b>\n\n"
            f"Со следующего дня буду присылать напоминания в это время.",
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer(
            "Произошла ошибка при сохранении времени. Попробуй ещё раз."
        )