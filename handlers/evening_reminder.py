from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import (
    get_or_create_user,
    get_question_for_date,
    create_question,
    create_answer,
    get_answer_for_year
)
from states import EveningReminderStates, MorningYesterdayStates

router = Router()


@router.callback_query(F.data == "evening_answer_today")
async def evening_answer_today(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Ответить за сегодня' в вечернем напоминании."""
    await callback.answer()

    # Получаем данные пользователя
    user = await get_or_create_user(callback.from_user.id)
    now = datetime.now()
    date_key = now.strftime("%m-%d")
    current_year = now.year

    # Проверяем есть ли вопрос
    question = await get_question_for_date(user.id, date_key)

    if not question:
        await callback.message.answer(
            "⚠️ Произошла ошибка. Вопрос для сегодня не найден."
        )
        await state.clear()
        return

    # Сохраняем данные в state
    await state.update_data(
        question_id=question.id,
        user_db_id=user.id,
        current_year=current_year,
        date_key=date_key,
        full_date=now.strftime("%Y-%m-%d")
    )

    await callback.message.answer(
        f"Отлично! Напиши свой ответ за сегодня 👇"
    )

    await state.set_state(EveningReminderStates.waiting_for_evening_answer)


@router.callback_query(F.data == "evening_add_question")
async def evening_add_question(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Добавить вопрос и ответ' в вечернем напоминании."""
    await callback.answer()

    # Получаем данные пользователя
    user = await get_or_create_user(callback.from_user.id)
    now = datetime.now()
    date_key = now.strftime("%m-%d")
    current_year = now.year

    # Сохраняем данные в state
    await state.update_data(
        user_db_id=user.id,
        current_year=current_year,
        date_key=date_key,
        full_date=now.strftime("%Y-%m-%d")
    )

    await callback.message.answer(
        "Напиши, пожалуйста, вопрос дня, который хочешь задавать себе каждый год в сегодняшнюю дату."
    )

    await state.set_state(EveningReminderStates.waiting_for_evening_question)


@router.callback_query(F.data == "evening_skip")
async def evening_skip(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Пропустить' в вечернем напоминании."""
    await callback.answer()

    await callback.message.answer(
        "Ок, пропускаем этот день. Вернусь завтра 💚"
    )

    await state.clear()


@router.message(EveningReminderStates.waiting_for_evening_answer)
async def process_evening_answer(message: Message, state: FSMContext):
    """Обработка ответа в вечернем режиме (когда вопрос уже есть)."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    current_year = data.get("current_year")
    full_date = data.get("full_date")

    # Проверяем, нет ли уже ответа за этот год (на случай race condition)
    existing_answer = await get_answer_for_year(user_db_id, question_id, current_year)

    if existing_answer:
        await message.answer(
            "На этот год ответ уже сохранён ✅"
        )
        await state.clear()
        return

    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, current_year)

    await message.answer(
        f"Супер, ответ за сегодня сохранён ✅"
    )

    await state.clear()


@router.message(EveningReminderStates.waiting_for_evening_question)
async def process_evening_question(message: Message, state: FSMContext):
    """Обработка вопроса в вечернем режиме (когда вопроса ещё нет)."""
    question_text = message.text.strip()

    if not question_text:
        await message.answer("Вопрос не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    date_key = data.get("date_key")

    # Создаём вопрос
    question = await create_question(user_db_id, date_key, question_text)

    # Сохраняем ID вопроса в state
    await state.update_data(question_id=question.id)

    await message.answer(
        "Отлично, вопрос сохранён ✅\n\n"
        "Теперь напиши свой ответ за сегодня 👇"
    )

    await state.set_state(EveningReminderStates.waiting_for_evening_answer_after_question)


@router.message(EveningReminderStates.waiting_for_evening_answer_after_question)
async def process_evening_answer_after_question(message: Message, state: FSMContext):
    """Обработка ответа после создания вопроса в вечернем режиме."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    current_year = data.get("current_year")
    full_date = data.get("full_date")

    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, current_year)

    await message.answer(
        f"Супер, ответ за сегодня сохранён ✅"
    )

    await state.clear()


# ============================================================================
# Обработчики для утреннего напоминания в 09:00 про вчерашний день
# ============================================================================


@router.callback_query(F.data.startswith("morning_yesterday_answer:"))
async def morning_yesterday_answer(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Записать ответ за вчера' в утреннем напоминании."""
    await callback.answer()

    # Извлекаем date_key из callback_data (формат: morning_yesterday_answer:MM-DD:YYYY)
    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])

    # Получаем данные пользователя
    user = await get_or_create_user(callback.from_user.id)

    # Проверяем есть ли вопрос
    question = await get_question_for_date(user.id, date_key)

    if not question:
        await callback.message.answer(
            "⚠️ Произошла ошибка. Вопрос для вчерашнего дня не найден."
        )
        await state.clear()
        return

    # Сохраняем данные в state
    await state.update_data(
        question_id=question.id,
        user_db_id=user.id,
        yesterday_year=year,
        date_key=date_key,
        full_date=f"{year}-{date_key}"
    )

    await callback.message.answer(
        f"Отлично! Напиши свой ответ за вчера 👇"
    )

    await state.set_state(MorningYesterdayStates.waiting_for_yesterday_answer)


@router.callback_query(F.data.startswith("morning_yesterday_add:"))
async def morning_yesterday_add_question(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Добавить вопрос и ответ за вчера' в утреннем напоминании."""
    await callback.answer()

    # Извлекаем date_key из callback_data (формат: morning_yesterday_add:MM-DD:YYYY)
    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])

    # Получаем данные пользователя
    user = await get_or_create_user(callback.from_user.id)

    # Сохраняем данные в state
    await state.update_data(
        user_db_id=user.id,
        yesterday_year=year,
        date_key=date_key,
        full_date=f"{year}-{date_key}"
    )

    await callback.message.answer(
        "Напиши, пожалуйста, вопрос, который хочешь задавать себе каждый год во вчерашнюю дату."
    )

    await state.set_state(MorningYesterdayStates.waiting_for_yesterday_question)


@router.callback_query(F.data == "morning_yesterday_skip")
async def morning_yesterday_skip(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Пропустить вчера' в утреннем напоминании."""
    await callback.answer()

    await callback.message.answer(
        "Ок, пропускаем вчерашний день. Продолжим с сегодняшнего 💚"
    )

    await state.clear()


@router.message(MorningYesterdayStates.waiting_for_yesterday_answer)
async def process_yesterday_answer(message: Message, state: FSMContext):
    """Обработка ответа за вчерашний день в утреннем режиме."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    yesterday_year = data.get("yesterday_year")
    full_date = data.get("full_date")

    # Проверяем, нет ли уже ответа за этот год
    existing_answer = await get_answer_for_year(user_db_id, question_id, yesterday_year)

    if existing_answer:
        await message.answer(
            "На вчерашний день ответ уже сохранён ✅"
        )
        await state.clear()
        return

    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, yesterday_year)

    await message.answer(
        f"Супер, ответ за вчера сохранён ✅"
    )

    await state.clear()


@router.message(MorningYesterdayStates.waiting_for_yesterday_question)
async def process_yesterday_question(message: Message, state: FSMContext):
    """Обработка вопроса за вчерашний день в утреннем режиме."""
    question_text = message.text.strip()

    if not question_text:
        await message.answer("Вопрос не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    date_key = data.get("date_key")

    # Создаём вопрос
    question = await create_question(user_db_id, date_key, question_text)

    # Сохраняем ID вопроса в state
    await state.update_data(question_id=question.id)

    await message.answer(
        "Отлично, вопрос сохранён ✅\n\n"
        "Теперь напиши свой ответ за вчера 👇"
    )

    await state.set_state(MorningYesterdayStates.waiting_for_yesterday_answer_after_question)


@router.message(MorningYesterdayStates.waiting_for_yesterday_answer_after_question)
async def process_yesterday_answer_after_question(message: Message, state: FSMContext):
    """Обработка ответа после создания вопроса за вчерашний день."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    yesterday_year = data.get("yesterday_year")
    full_date = data.get("full_date")

    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, yesterday_year)

    await message.answer(
        f"Супер, ответ за вчера сохранён ✅"
    )

    await state.clear()
