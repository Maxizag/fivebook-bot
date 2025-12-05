from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import get_or_create_user, get_question_for_date, get_answers_for_question, create_question, create_answer
from states import DateViewStates, BackdatedEntryStates

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


async def _render_date_view(target: Message | CallbackQuery, date_key: str, state: FSMContext = None):
    """Отображает вопрос и ответы для указанной даты."""
    telegram_id = target.from_user.id
    user = await get_or_create_user(telegram_id)
    question = await get_question_for_date(user.id, date_key)
    answers = await get_answers_for_question(question.id) if question else []

    date_label = _format_date_label(date_key)
    lines: list[str] = [f"📅 Дата: <b>{date_label}</b>"]

    # Проверяем, является ли выбранная дата не позже сегодня
    today = datetime.now()
    selected_date = datetime.strptime(f"{today.year}-{date_key}", "%Y-%m-%d")
    is_past_or_today = selected_date.date() <= today.date()

    if question:
        lines.append(f"<b>Вопрос:</b>\n{question.question_text}")
        if answers:
            lines.append("<b>Ответы по годам:</b>")
            for answer in answers:
                lines.append(f"• <b>{answer.year}</b>: {answer.answer_text}")
        else:
            lines.append("Ответов пока нет. ✍️")
    else:
        lines.append(
            f"Для даты {date_label} у тебя пока нет вопроса в пятибуке.\n"
            "Вопрос появится, когда ты впервые ответишь в эту дату."
        )

    text = "\n\n".join(lines)

    # Строим клавиатуру
    keyboard_buttons = []

    # Добавляем кнопку "Добавить вопрос и ответ" только если нет вопроса и дата не позже сегодня
    if not question and is_past_or_today:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="✍️ Добавить вопрос и ответ за эту дату",
                callback_data=f"add_backdated:{date_key}"
            )
        ])

    # Добавляем навигационные кнопки
    prev_key = _shift_date_key(date_key, -1)
    next_key = _shift_date_key(date_key, 1)
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"◀ {_format_date_label(prev_key)}",
            callback_data=f"date_prev:{date_key}"
        ),
        InlineKeyboardButton(
            text=f"{_format_date_label(next_key)} ▶",
            callback_data=f"date_next:{date_key}"
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
    current_date_key = callback.data.split(":", 1)[1]
    prev_date_key = _shift_date_key(current_date_key, -1)
    await _render_date_view(callback, prev_date_key)


@router.callback_query(F.data.startswith("date_next:"))
async def show_next_day(callback: CallbackQuery):
    """Перейти к следующему дню."""
    await callback.answer()
    current_date_key = callback.data.split(":", 1)[1]
    next_date_key = _shift_date_key(current_date_key, 1)
    await _render_date_view(callback, next_date_key)


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

