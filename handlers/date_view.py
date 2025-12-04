from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import get_or_create_user, get_question_for_date, get_answers_for_question
from states import DateViewStates

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


def _build_navigation_keyboard(current_date_key: str) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру навигации с кнопками предыдущего и следующего дня."""
    prev_key = _shift_date_key(current_date_key, -1)
    next_key = _shift_date_key(current_date_key, 1)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"◀ {_format_date_label(prev_key)}",
                    callback_data=f"date_prev:{current_date_key}"
                ),
                InlineKeyboardButton(
                    text=f"{_format_date_label(next_key)} ▶",
                    callback_data=f"date_next:{current_date_key}"
                )
            ]
        ]
    )


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


async def _render_date_view(target: Message | CallbackQuery, date_key: str):
    """Отображает вопрос и ответы для указанной даты."""
    telegram_id = target.from_user.id
    user = await get_or_create_user(telegram_id)
    question = await get_question_for_date(user.id, date_key)
    answers = await get_answers_for_question(question.id) if question else []

    date_label = _format_date_label(date_key)
    lines: list[str] = [f"📅 Дата: <b>{date_label}</b>"]

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
    keyboard = _build_navigation_keyboard(date_key)

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

