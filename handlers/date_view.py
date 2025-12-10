from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_or_create_user,
    get_question_for_date,
    get_answers_for_question,
    create_question,
    create_answer,
    get_answer_for_year
)
from states import DateViewStates, BackdatedEntryStates, CalendarQuestionStates, CalendarAnswerStates, CalendarEditStates

router = Router()

_BASE_YEAR = 2024  # високосный год, чтобы корректно работать с 29 февраля


def _format_date_label(date_key: str) -> str:
    """Возвращает строку в формате ДД.ММ для отображения пользователю."""
    date_obj = datetime.strptime(f"{_BASE_YEAR}-{date_key}", "%Y-%m-%d")
    return date_obj.strftime("%d.%m")


def _shift_date_key(date_key: str, days: int) -> str:
    """Смещает date_key на указанное количество дней с учётом кругового перехода."""
    date_obj = datetime.strptime(f"{_BASE_YEAR}-{date_key}", "%Y-%m-%d")
    shifted = date_obj + timedelta(days=days)
    return shifted.strftime("%m-%d")


def _parse_user_date(date_text: str) -> str | None:
    """Парсит пользовательский ввод ДД.ММ и возвращает date_key (MM-DD)."""
    normalized = (
        date_text.strip()
        .replace("/", ".")
        .replace("-", ".")
        .replace(",", ".")
    )
    if len(normalized) != 5 or normalized[2] != ".":
        return None
    try:
        # Используем високосный год, чтобы разрешить 29 февраля
        date_obj = datetime.strptime(f"{normalized}.2024", "%d.%m.%Y")
    except ValueError:
        return None
    return date_obj.strftime("%m-%d")


async def _render_date_view(target: Message | CallbackQuery, date_key: str, year: int = None, state: FSMContext = None):
    """Отображает вопрос и ответы для указанной даты и года."""
    telegram_id = target.from_user.id
    user = await get_or_create_user(telegram_id)
    question = await get_question_for_date(user.id, date_key)

    # Если год не указан, используем текущий год
    if year is None:
        year = datetime.now().year

    date_label = _format_date_label(date_key)

    # Строим клавиатуру
    keyboard_buttons = []

    # Сценарий 1: Вопроса нет
    if not question:
        text = (
            f"📅 Дата: <b>{date_label}</b>\n\n"
            f"Для даты {date_label} у тебя пока нет вопроса.\n"
            f"Хочешь создать вопрос для этой даты?"
        )

        # Кнопки: Создать вопрос | Назад
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="➕ Создать вопрос",
                callback_data=f"calendar_create_question:{date_key}:{year}"
            )
        ])
    else:
        # Проверяем наличие ответа за выбранный год
        answer = await get_answer_for_year(user.id, question.id, year)

        # Сценарий 2: Вопрос есть, но ответа за выбранный год нет
        if not answer:
            text = (
                f"📅 Дата: <b>{date_label}</b>\n"
                f"📆 Год: <b>{year}</b>\n\n"
                f"<b>Вопрос:</b>\n{question.question_text}\n\n"
                f"У тебя нет ответа за {year} для даты {date_label}.\n"
                f"Хочешь записать?"
            )

            # Кнопки: Записать ответ | Назад
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="✍️ Записать ответ",
                    callback_data=f"calendar_add_answer:{date_key}:{year}:{question.id}"
                )
            ])
        else:
            # Сценарий 3: Вопрос и ответ есть
            text = (
                f"📅 Дата: <b>{date_label}</b>\n"
                f"📆 Год: <b>{year}</b>\n\n"
                f"<b>Вопрос:</b>\n{question.question_text}\n\n"
                f"<b>Ответ:</b>\n{answer.answer_text}"
            )

            # Проверяем, прошло ли меньше 24 часов с момента создания ответа
            time_since_creation = datetime.utcnow() - answer.created_at
            can_edit = time_since_creation.total_seconds() < 24 * 3600

            # Кнопки: Изменить | Удалить (только если <24 часов)
            if can_edit:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="✏️ Изменить",
                        callback_data=f"calendar_edit_answer:{date_key}:{year}:{answer.id}"
                    ),
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"calendar_delete_answer:{date_key}:{year}:{answer.id}"
                    )
                ])

    # Добавляем кнопку "Назад" для всех сценариев
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="↩️ Назад",
            callback_data=f"calendar_back:{date_key}:{year}"
        )
    ])

    # Добавляем навигационные кнопки (с сохранением года)
    prev_key = _shift_date_key(date_key, -1)
    next_key = _shift_date_key(date_key, 1)
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"◀ {_format_date_label(prev_key)}",
            callback_data=f"date_prev:{date_key}:{year}"
        ),
        InlineKeyboardButton(
            text=f"{_format_date_label(next_key)} ▶",
            callback_data=f"date_next:{date_key}:{year}"
        )
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("date"))
async def cmd_date(message: Message, state: FSMContext):
    """Запрос даты для просмотра вопросов и ответов."""
    await message.answer(
        "Введи дату в формате <b>ДД.ММ</b>, например: <b>05.03</b>",
        parse_mode="HTML"
    )
    await state.set_state(DateViewStates.waiting_for_date)


@router.message(DateViewStates.waiting_for_date)
async def process_date_input(message: Message, state: FSMContext):
    """Обработка пользовательского ввода даты."""
    date_key = _parse_user_date(message.text or "")
    if not date_key:
        await message.answer(
            "Не понимаю эту дату. Пожалуйста, введи в формате <b>ДД.ММ</b>, например 05.03",
            parse_mode="HTML"
        )
        return

    await _render_date_view(message, date_key)
    await state.clear()


@router.callback_query(F.data.startswith("date_prev:"))
async def show_previous_day(callback: CallbackQuery):
    """Перейти к предыдущему дню."""
    await callback.answer()
    parts = callback.data.split(":")
    current_date_key = parts[1]
    year = int(parts[2]) if len(parts) > 2 else datetime.now().year
    prev_date_key = _shift_date_key(current_date_key, -1)
    await _render_date_view(callback, prev_date_key, year)


@router.callback_query(F.data.startswith("date_next:"))
async def show_next_day(callback: CallbackQuery):
    """Перейти к следующему дню."""
    await callback.answer()
    parts = callback.data.split(":")
    current_date_key = parts[1]
    year = int(parts[2]) if len(parts) > 2 else datetime.now().year
    next_date_key = _shift_date_key(current_date_key, 1)
    await _render_date_view(callback, next_date_key, year)


@router.callback_query(F.data.startswith("add_backdated:"))
async def add_backdated_entry(callback: CallbackQuery, state: FSMContext):
    """Начать создание вопроса и ответа задним числом."""
    await callback.answer()

    # Извлекаем date_key из callback_data
    date_key = callback.data.split(":", 1)[1]
    date_label = _format_date_label(date_key)

    # Получаем год выбранной даты
    today = datetime.now()
    selected_date = datetime.strptime(f"{today.year}-{date_key}", "%Y-%m-%d")

    # Проверяем что дата не в будущем
    if selected_date.date() > today.date():
        await callback.message.answer(
            "⚠️ Нельзя создавать записи для будущих дат.\n\n"
            "Выбери дату не позже сегодняшней."
        )
        return

    # Сохраняем информацию о выбранной дате в state
    user = await get_or_create_user(callback.from_user.id)
    await state.update_data(
        backdated_date_key=date_key,
        backdated_date_label=date_label,
        backdated_full_date=selected_date.strftime("%Y-%m-%d"),
        backdated_year=selected_date.year,
        user_db_id=user.id
    )

    await callback.message.answer(
        f"Напиши, пожалуйста, вопрос, который хочешь задавать себе каждый год в дату {date_label}."
    )

    await state.set_state(BackdatedEntryStates.waiting_for_backdated_question)


@router.message(BackdatedEntryStates.waiting_for_backdated_question)
async def process_backdated_question(message: Message, state: FSMContext):
    """Обработка вопроса для записи задним числом."""
    question_text = message.text.strip()

    if not question_text:
        await message.answer("Вопрос не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    date_key = data.get("backdated_date_key")
    date_label = data.get("backdated_date_label")
    user_db_id = data.get("user_db_id")
    backdated_year = data.get("backdated_year")

    # Создаём вопрос
    question = await create_question(user_db_id, date_key, question_text)

    # Сохраняем ID вопроса в state
    await state.update_data(question_id=question.id)

    await message.answer(
        f"Отлично, вопрос сохранён ✅\n\n"
        f"А теперь напиши свой ответ за {date_label}.{backdated_year} 👇"
    )

    await state.set_state(BackdatedEntryStates.waiting_for_backdated_answer)


@router.message(BackdatedEntryStates.waiting_for_backdated_answer)
async def process_backdated_answer(message: Message, state: FSMContext):
    """Обработка ответа для записи задним числом."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    backdated_full_date = data.get("backdated_full_date")
    backdated_year = data.get("backdated_year")
    date_label = data.get("backdated_date_label")

    # Создаём ответ с датой выбранного дня
    await create_answer(user_db_id, question_id, answer_text, backdated_full_date, backdated_year)

    await message.answer(
        f"Ответ за {date_label}.{backdated_year} сохранён ✅"
    )

    await state.clear()


# ============================================================================
# Обработчики для новой логики календаря с возможностью редактирования
# ============================================================================


@router.callback_query(F.data.startswith("calendar_back:"))
async def calendar_back(callback: CallbackQuery):
    """Возврат к просмотру даты."""
    await callback.answer()
    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])
    await _render_date_view(callback, date_key, year)


@router.callback_query(F.data.startswith("calendar_create_question:"))
async def calendar_create_question(callback: CallbackQuery, state: FSMContext):
    """Начать создание вопроса через календарь."""
    await callback.answer()

    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])
    date_label = _format_date_label(date_key)

    # Сохраняем информацию в state
    user = await get_or_create_user(callback.from_user.id)
    await state.update_data(
        calendar_date_key=date_key,
        calendar_year=year,
        calendar_date_label=date_label,
        user_db_id=user.id
    )

    await callback.message.answer(
        f"Напиши, пожалуйста, вопрос, который хочешь задавать себе каждый год в дату {date_label}."
    )

    await state.set_state(CalendarQuestionStates.waiting_for_question)


@router.message(CalendarQuestionStates.waiting_for_question)
async def process_calendar_question(message: Message, state: FSMContext):
    """Обработка вопроса, созданного через календарь."""
    question_text = message.text.strip()

    if not question_text:
        await message.answer("Вопрос не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    date_key = data.get("calendar_date_key")
    year = data.get("calendar_year")
    date_label = data.get("calendar_date_label")
    user_db_id = data.get("user_db_id")

    # Создаём вопрос
    question = await create_question(user_db_id, date_key, question_text)

    # Сохраняем ID вопроса в state
    await state.update_data(question_id=question.id)

    await message.answer(
        f"Отлично, вопрос сохранён ✅\n\n"
        f"Теперь напиши свой ответ за {date_label}.{year} 👇"
    )

    await state.set_state(CalendarQuestionStates.waiting_for_answer_after_question)


@router.message(CalendarQuestionStates.waiting_for_answer_after_question)
async def process_calendar_answer_after_question(message: Message, state: FSMContext):
    """Обработка ответа после создания вопроса через календарь."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    date_key = data.get("calendar_date_key")
    year = data.get("calendar_year")
    date_label = data.get("calendar_date_label")

    # Формируем полную дату
    full_date = f"{year}-{date_key}"

    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, year)

    await message.answer(
        f"Супер! Вопрос и ответ за {date_label}.{year} сохранены ✅"
    )

    await state.clear()


@router.callback_query(F.data.startswith("calendar_add_answer:"))
async def calendar_add_answer(callback: CallbackQuery, state: FSMContext):
    """Начать добавление ответа через календарь."""
    await callback.answer()

    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])
    question_id = int(parts[3])
    date_label = _format_date_label(date_key)

    # Сохраняем информацию в state
    user = await get_or_create_user(callback.from_user.id)
    await state.update_data(
        calendar_date_key=date_key,
        calendar_year=year,
        calendar_date_label=date_label,
        question_id=question_id,
        user_db_id=user.id
    )

    await callback.message.answer(
        f"Напиши свой ответ за {date_label}.{year} 👇"
    )

    await state.set_state(CalendarAnswerStates.waiting_for_answer)


@router.message(CalendarAnswerStates.waiting_for_answer)
async def process_calendar_answer(message: Message, state: FSMContext):
    """Обработка ответа, добавленного через календарь."""
    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    date_key = data.get("calendar_date_key")
    year = data.get("calendar_year")
    date_label = data.get("calendar_date_label")

    # Формируем полную дату
    full_date = f"{year}-{date_key}"

    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, year)

    await message.answer(
        f"Ответ за {date_label}.{year} сохранён ✅"
    )

    await state.clear()


@router.callback_query(F.data.startswith("calendar_edit_answer:"))
async def calendar_edit_answer(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование ответа через календарь."""
    await callback.answer()

    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])
    answer_id = int(parts[3])
    date_label = _format_date_label(date_key)

    # Сохраняем информацию в state
    await state.update_data(
        calendar_date_key=date_key,
        calendar_year=year,
        calendar_date_label=date_label,
        answer_id=answer_id
    )

    await callback.message.answer(
        f"Напиши новый ответ за {date_label}.{year} 👇"
    )

    await state.set_state(CalendarEditStates.waiting_for_edited_answer)


@router.message(CalendarEditStates.waiting_for_edited_answer)
async def process_calendar_edited_answer(message: Message, state: FSMContext):
    """Обработка отредактированного ответа через календарь."""
    from database import update_answer_text

    answer_text = message.text.strip()

    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return

    data = await state.get_data()
    answer_id = data.get("answer_id")
    date_label = data.get("calendar_date_label")
    year = data.get("calendar_year")

    # Обновляем текст ответа
    await update_answer_text(answer_id, answer_text)

    await message.answer(
        f"Ответ за {date_label}.{year} обновлён ✅"
    )

    await state.clear()


@router.callback_query(F.data.startswith("calendar_delete_answer:"))
async def calendar_delete_answer(callback: CallbackQuery):
    """Удалить ответ через календарь."""
    from database import delete_answer

    await callback.answer()

    parts = callback.data.split(":")
    date_key = parts[1]
    year = int(parts[2])
    answer_id = int(parts[3])
    date_label = _format_date_label(date_key)

    # Удаляем ответ
    await delete_answer(answer_id)

    await callback.message.answer(
        f"Ответ за {date_label}.{year} удалён ✅"
    )

    # Возвращаемся к просмотру даты
    await _render_date_view(callback, date_key, year)

