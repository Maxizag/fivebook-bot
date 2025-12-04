from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from states import QuestionStates, PastYearsStates, EditAnswerStates
from database import (
    get_or_create_user,
    get_question_for_date,
    create_question,
    get_answers_for_question,
    get_answer_for_year,
    create_answer,
    update_answer_text,
    update_answer_year,
    delete_answer,
    get_answer_by_id
)
from utils import is_editable, get_time_left_str, is_leap_year, get_year_keyboard
from datetime import datetime



router = Router()


async def validate_and_process_year(
    year: int,
    state: FSMContext,
    mode: str,
    message_or_callback,
    date_key: str = None,
    user_db_id: int = None,
    question_id: int = None,
    current_year: int = None
) -> tuple[bool, str]:
    """
    Валидирует год и возвращает результат валидации
    
    Args:
        year: Год для валидации
        state: FSM контекст
        mode: Режим ('import', 'edit', 'change_year')
        message_or_callback: Message или CallbackQuery объект
        date_key: Ключ даты (MM-DD)
        user_db_id: ID пользователя в БД
        question_id: ID вопроса
        current_year: Текущий год
        
    Returns:
        tuple[bool, str]: (успех, сообщение об ошибке или None)
    """
    # Получаем данные из state если не переданы
    data = await state.get_data()
    if date_key is None:
        date_key = data.get("date_key")
    if user_db_id is None:
        user_db_id = data.get("user_db_id")
    if question_id is None:
        question_id = data.get("question_id")
    if current_year is None:
        current_year = data.get("current_year", datetime.now().year)
    
    # Проверка диапазона: 2019 <= year <= current_year
    if year < 2019:
        return False, f"Год должен быть не меньше 2019. Выбери другой год."
    
    if year > current_year:
        return False, f"Год должен быть не больше текущего ({current_year}). Выбери другой год."
    
    # Для режима импорта: год должен быть меньше текущего
    if mode == "import" and year >= current_year:
        return False, f"Для импорта год должен быть меньше текущего ({current_year}). Выбери другой год."
    
    # Проверка для 29 февраля - год должен быть високосным
    if date_key == "02-29" and not is_leap_year(year):
        return False, f"Год {year} не является високосным, поэтому ответ за 29 февраля в этот год внести нельзя."
    
    # Проверка уникальности (для импорта и изменения года)
    # Для режима "edit" не проверяем уникальность, так как мы ищем существующий ответ
    if mode in ("import", "change_year"):
        existing_answer = await get_answer_for_year(user_db_id, question_id, year)
        
        # Для изменения года проверяем что это не тот же ответ
        if mode == "change_year":
            edit_answer_id = data.get("edit_answer_id")
            if existing_answer and existing_answer.id != edit_answer_id:
                return False, f"Ответ за {year} год уже существует. Выбери другой год."
        elif existing_answer:
            return False, f"Ответ за {year} год уже существует. Выбери другой год."
    
    return True, None


async def show_daily_question(message: Message, state: FSMContext, date_key: str = None):
    """Показать вопрос дня (используется и для /today, и для напоминаний)"""
    user = await get_or_create_user(message.from_user.id)
    
    # Определяем дату
    if date_key is None:
        now = datetime.now()
        date_key = now.strftime("%m-%d")
        current_year = now.year
        full_date = now.strftime("%Y-%m-%d")
    else:
        # Для случая когда передаём дату извне (из scheduler)
        now = datetime.now()
        current_year = now.year
        full_date = now.strftime("%Y-%m-%d")
    
    # Сохраняем контекст в state
    await state.update_data(
        date_key=date_key,
        current_year=current_year,
        full_date=full_date,
        user_db_id=user.id
    )
    
    # Проверяем, есть ли вопрос для этой даты
    question = await get_question_for_date(user.id, date_key)
    
    if question is None:
        # Сценарий A: Первый год, вопрос не создан
        await message.answer(
            "Привет! Время для записи в пятибук 🌿\n\n"
            "Сегодня у тебя ещё нет вопроса для этого дня.\n"
            "Напиши, пожалуйста, вопрос дня, который хочешь задавать себе каждый год в эту дату."
        )
        await state.set_state(QuestionStates.waiting_for_question)
    else:
        # Сценарий B: Вопрос уже существует
        await state.update_data(question_id=question.id)
        
        # Проверяем, есть ли уже ответ за текущий год
        existing_answer = await get_answer_for_year(user.id, question.id, current_year)
        
        if existing_answer:
            # Ответ уже есть
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📖 Посмотреть прошлые ответы",
                    callback_data="show_past_answers"
                )],
                [InlineKeyboardButton(
                    text="➕ Добавить ответы за прошлые годы",
                    callback_data="add_past_years"
                )]
            ])
            
            await message.answer(
                f"Сегодняшний вопрос:\n\n"
                f"<b>{question.question_text}</b>\n\n"
                f"Ты уже ответила на этот вопрос в {current_year} году ✅\n\n"
                f"Твой ответ:\n{existing_answer.answer_text}",
                parse_mode="HTML",
                reply_markup=keyboard
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
                )],
                [InlineKeyboardButton(
                    text="➕ Добавить ответы за прошлые годы",
                    callback_data="add_past_years"
                )]
            ])
            
            await message.answer(
                f"Сегодняшний вопрос для тебя:\n\n"
                f"<b>{question.question_text}</b>\n\n"
                f"Хочешь сначала посмотреть прошлые ответы или сразу написать новый?",
                parse_mode="HTML",
                reply_markup=keyboard
            )


@router.message(QuestionStates.waiting_for_question)
async def process_new_question(message: Message, state: FSMContext):
    """Обработка нового вопроса"""
    question_text = message.text.strip()
    
    if not question_text:
        await message.answer("Вопрос не может быть пустым. Попробуй ещё раз.")
        return
    
    data = await state.get_data()
    date_key = data.get("date_key")
    user_db_id = data.get("user_db_id")
    
    # Создаём вопрос
    question = await create_question(user_db_id, date_key, question_text)
    
    await state.update_data(question_id=question.id)
    
    await message.answer(
        "Отлично, вопрос сохранён ✅\n\n"
        "Теперь напиши свой ответ за этот год."
    )
    
    await state.set_state(QuestionStates.waiting_for_answer)


@router.message(QuestionStates.waiting_for_answer)
async def process_answer(message: Message, state: FSMContext):
    """Обработка ответа на вопрос"""
    answer_text = message.text.strip()
    
    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return
    
    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    current_year = data.get("current_year")
    full_date = data.get("full_date")
    
    # Проверяем, нет ли уже ответа за этот год
    existing_answer = await get_answer_for_year(user_db_id, question_id, current_year)
    
    if existing_answer:
        await message.answer(
            f"На этот год ответ уже сохранён ✅\n\n"
            f"Функцию редактирования добавим позже."
        )
        await state.clear()
        return
    
    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, full_date, current_year)
    
    # Проверяем, сколько это по счёту ответ (первый или нет)
    all_answers = await get_answers_for_question(question_id)
    
    if len(all_answers) == 1:
        # Первый ответ - предлагаем внести прошлые годы
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="➕ Внести прошлые годы",
                callback_data="add_past_years"
            )],
            [InlineKeyboardButton(
                text="⏭ Нет, на сегодня хватит",
                callback_data="skip_past_years"
            )]
        ])
        
        await message.answer(
            "Записано 💚\n\n"
            "Хочешь добавить свои ответы за прошлые годы из бумажного пятибука, "
            "чтобы я показывал тебе полную историю?",
            reply_markup=keyboard
        )
    else:
        # Не первый ответ
        await message.answer(
            f"Супер, ответ за {current_year} сохранён ✅"
        )
        await state.clear()


@router.callback_query(F.data == "show_past_answers")
async def show_past_answers(callback: CallbackQuery, state: FSMContext):
    """Показать прошлые ответы"""
    await callback.answer()
    
    data = await state.get_data()
    question_id = data.get("question_id")
    current_year = data.get("current_year")
    
    if not question_id:
        await callback.message.answer("Произошла ошибка. Попробуй команду /today")
        return
    
    # Получаем все ответы
    answers = await get_answers_for_question(question_id)
    
    if not answers:
        await callback.message.answer(
            "У тебя пока нет ответов на этот вопрос.\n"
            "Напиши свой первый ответ! ✍️"
        )
        await state.set_state(QuestionStates.waiting_for_answer)
        return
    
    # Формируем список ответов
    answers_text = "Твои ответы в этот день:\n\n"
    for answer in answers:
        answers_text += f"• <b>{answer.year}</b>: {answer.answer_text}\n\n"
    
    # Проверяем, есть ли ответ за текущий год
    has_current_year = any(a.year == current_year for a in answers)
    
    if has_current_year:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✏️ Изменить/удалить ответ",
            callback_data="edit_answer"
        )]
    ])
    
        await callback.message.answer(
        answers_text + "На этот год ответ уже есть ✅",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    else:
        await callback.message.answer(
            answers_text + "Теперь напиши свой ответ за этот год 👇",
            parse_mode="HTML"
        )
        await state.set_state(QuestionStates.waiting_for_answer)


@router.callback_query(F.data == "write_answer")
async def write_answer_callback(callback: CallbackQuery, state: FSMContext):
    """Начать писать ответ"""
    await callback.answer()
    
    data = await state.get_data()
    current_year = data.get("current_year")
    
    await callback.message.answer(
        f"Отлично! Напиши свой ответ за {current_year} год 👇"
    )
    
    await state.set_state(QuestionStates.waiting_for_answer)


@router.callback_query(F.data == "add_past_years")
async def add_past_years_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление ответов за прошлые годы"""
    await callback.answer()
    
    # Проверяем что в state есть все нужные данные
    data = await state.get_data()
    if not data.get("question_id") or not data.get("date_key"):
        await callback.message.answer("Произошла ошибка. Попробуй команду /today")
        return
    
    # Сохраняем режим выбора года
    await state.update_data(year_selection_mode="import")
    
    year_keyboard = get_year_keyboard()
    
    await callback.message.answer(
        "За какой год хочешь внести ответ?\n\n"
        "Выбери год из списка или напиши год вручную:",
        parse_mode="HTML",
        reply_markup=year_keyboard
    )
    
    await state.set_state(PastYearsStates.waiting_for_year)


@router.callback_query(F.data == "skip_past_years")
async def skip_past_years(callback: CallbackQuery, state: FSMContext):
    """Пропустить ввод прошлых годов"""
    await callback.answer()
    
    await callback.message.answer(
        "Хорошо! Ты всегда можешь добавить прошлые ответы позже через команду /today 💚"
    )
    
    await state.clear()


@router.callback_query(F.data.startswith("select_year:"))
async def process_year_selection_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора года через callback"""
    await callback.answer()
    
    # Извлекаем год из callback_data
    year_str = callback.data.split(":")[1]
    try:
        year = int(year_str)
    except ValueError:
        await callback.message.answer("Ошибка: неверный формат года")
        return
    
    # Определяем режим из state
    data = await state.get_data()
    mode = data.get("year_selection_mode", "import")
    
    # Валидация года
    is_valid, error_msg = await validate_and_process_year(
        year=year,
        state=state,
        mode=mode,
        message_or_callback=callback,
        date_key=data.get("date_key"),
        user_db_id=data.get("user_db_id"),
        question_id=data.get("question_id"),
        current_year=data.get("current_year", datetime.now().year)
    )
    
    if not is_valid:
        year_keyboard = get_year_keyboard()
        await callback.message.answer(
            f"{error_msg}\n\nВыбери другой год:",
            reply_markup=year_keyboard
        )
        return
    
    # Обработка в зависимости от режима
    if mode == "import":
        # Сохраняем год в state и просим ответ
        await state.update_data(past_year=year)
        await callback.message.answer(
            f"Напиши свой ответ за {year} год 👇"
        )
        await state.set_state(PastYearsStates.waiting_for_past_answer)
        
    elif mode == "edit":
        # Показываем ответ за выбранный год
        user_db_id = data.get("user_db_id")
        question_id = data.get("question_id")
        answer = await get_answer_for_year(user_db_id, question_id, year)
        
        if not answer:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_today"
                )]
            ])
            await callback.message.answer(
                f"Ответа за {year} год нет.\n\n"
                f"Попробуй другой год или вернись назад.",
                reply_markup=keyboard
            )
            return
        
        # Сохраняем ID ответа в state
        await state.update_data(edit_answer_id=answer.id, edit_answer_year=year)
        
        # Проверяем лимит 24 часа
        if is_editable(answer):
            # Можно редактировать
            time_left = get_time_left_str(answer)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✏️ Изменить текст",
                    callback_data="edit_text"
                )],
                [InlineKeyboardButton(
                    text="📅 Изменить год",
                    callback_data="edit_year"
                )],
                [InlineKeyboardButton(
                    text="🗑 Удалить ответ",
                    callback_data="delete_answer"
                )],
                [InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_today"
                )]
            ])
            
            await callback.message.answer(
                f"Сейчас у тебя сохранён ответ за {year} год:\n\n"
                f"<i>{answer.answer_text}</i>\n\n"
                f"⏰ На редактирование {time_left}\n\n"
                f"Что хочешь сделать?",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            # Прошло больше 24 часов
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_today"
                )]
            ])
            
            await callback.message.answer(
                f"Ответ за {year} год нельзя изменить или удалить — "
                f"он был сохранён более 24 часов назад.\n\n"
                f"В пятибуке ответы фиксируются как часть истории 💛",
                reply_markup=keyboard
            )
    
    elif mode == "change_year":
        # Изменяем год ответа
        answer_id = data.get("edit_answer_id")
        old_year = data.get("edit_answer_year")
        date_key = data.get("date_key")
        
        # Обновляем год
        success = await update_answer_year(answer_id, year, date_key)
        
        if success:
            await callback.message.answer(
                f"Год для этого ответа изменён с {old_year} на {year} ✅"
            )
        else:
            await callback.message.answer(
                "Произошла ошибка при обновлении. Попробуй ещё раз."
            )
        
        await state.clear()


@router.message(PastYearsStates.waiting_for_year)
async def process_past_year(message: Message, state: FSMContext):
    """Обработка ввода года для прошлого ответа (ручной ввод)"""
    
    year_text = message.text.strip()
    
    # Проверка что это число
    try:
        year = int(year_text)
    except ValueError:
        year_keyboard = get_year_keyboard()
        await message.answer(
            "Пожалуйста, выбери год из списка или введи год числом (2019-текущий):",
            parse_mode="HTML",
            reply_markup=year_keyboard
        )
        return
    
    # Валидация года
    data = await state.get_data()
    is_valid, error_msg = await validate_and_process_year(
        year=year,
        state=state,
        mode="import",
        message_or_callback=message,
        date_key=data.get("date_key"),
        user_db_id=data.get("user_db_id"),
        question_id=data.get("question_id"),
        current_year=data.get("current_year")
    )
    
    if not is_valid:
        year_keyboard = get_year_keyboard()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Выбрать другой год",
                callback_data="add_past_years"
            )],
            [InlineKeyboardButton(
                text="Закончить",
                callback_data="finish_past_years"
            )]
        ])
        await message.answer(
            f"{error_msg}\n\n"
            f"Выбери год из списка или попробуй другой:",
            reply_markup=year_keyboard
        )
        return
    
    # Сохраняем год в state и просим ответ
    await state.update_data(past_year=year)
    
    await message.answer(
        f"Напиши свой ответ за {year} год 👇"
    )
    
    await state.set_state(PastYearsStates.waiting_for_past_answer)


@router.message(PastYearsStates.waiting_for_past_answer)
async def process_past_answer(message: Message, state: FSMContext):
    """Обработка ответа за прошлый год"""
    answer_text = message.text.strip()
    
    if not answer_text:
        await message.answer("Ответ не может быть пустым. Попробуй ещё раз.")
        return
    
    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    past_year = data.get("past_year")
    date_key = data.get("date_key")
    
    # Формируем полную дату для прошлого года
    past_date = f"{past_year}-{date_key}"
    
    # Создаём ответ
    await create_answer(user_db_id, question_id, answer_text, past_date, past_year)
    
    # Предлагаем добавить ещё или закончить
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="➕ Добавить ещё год",
            callback_data="add_past_years"
        )],
        [InlineKeyboardButton(
            text="✅ Закончить",
            callback_data="finish_past_years"
        )]
    ])
    
    await message.answer(
        f"Ответ за {past_year} сохранён ✅\n\n"
        f"Хочешь добавить ещё один год?",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "finish_past_years")
async def finish_past_years(callback: CallbackQuery, state: FSMContext):
    """Завершить ввод прошлых годов"""
    await callback.answer()
    
    await callback.message.answer(
        "Готово 💚\n\n"
        "Теперь в эту дату я буду показывать тебе все сохранённые ответы за прошлые годы."
    )
    
    await state.clear()

@router.callback_query(F.data == "edit_answer")
async def edit_answer_start(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование/удаление ответа"""
    await callback.answer()
    
    # Сохраняем режим выбора года
    await state.update_data(year_selection_mode="edit")
    
    year_keyboard = get_year_keyboard()
    
    await callback.message.answer(
        "За какой год хочешь изменить или удалить ответ?\n\n"
        "Выбери год из списка или напиши год вручную:",
        parse_mode="HTML",
        reply_markup=year_keyboard
    )
    
    await state.set_state(EditAnswerStates.waiting_for_year_to_edit)


@router.message(EditAnswerStates.waiting_for_year_to_edit)
async def process_year_to_edit(message: Message, state: FSMContext):
    """Обработка выбора года для редактирования"""
    year_text = message.text.strip()
    
    # Проверка что это число
    try:
        year = int(year_text)
    except ValueError:
        await message.answer(
            "Пожалуйста, введи год числом, например: <b>2021</b>",
            parse_mode="HTML"
        )
        return
    
    data = await state.get_data()
    user_db_id = data.get("user_db_id")
    question_id = data.get("question_id")
    
    # Ищем ответ за этот год
    answer = await get_answer_for_year(user_db_id, question_id, year)
    
    if not answer:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_to_today"
            )]
        ])
        
        await message.answer(
            f"Ответа за {year} год нет.\n\n"
            f"Попробуй другой год или вернись назад.",
            reply_markup=keyboard
        )
        return
    
    # Сохраняем ID ответа в state
    await state.update_data(edit_answer_id=answer.id, edit_answer_year=year)
    
    # Проверяем лимит 24 часа
    if is_editable(answer):
        # Можно редактировать
        time_left = get_time_left_str(answer)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✏️ Изменить текст",
                callback_data="edit_text"
            )],
            [InlineKeyboardButton(
                text="📅 Изменить год",
                callback_data="edit_year"
            )],
            [InlineKeyboardButton(
                text="🗑 Удалить ответ",
                callback_data="delete_answer"
            )],
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_to_today"
            )]
        ])
        
        await message.answer(
            f"Сейчас у тебя сохранён ответ за {year} год:\n\n"
            f"<i>{answer.answer_text}</i>\n\n"
            f"⏰ На редактирование {time_left}\n\n"
            f"Что хочешь сделать?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        # Прошло больше 24 часов
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_to_today"
            )]
        ])
        
        await message.answer(
            f"Ответ за {year} год нельзя изменить или удалить — "
            f"он был сохранён более 24 часов назад.\n\n"
            f"В пятибуке ответы фиксируются как часть истории 💛",
            reply_markup=keyboard
        )


@router.callback_query(F.data == "edit_text")
async def edit_text_start(callback: CallbackQuery, state: FSMContext):
    """Начать изменение текста ответа"""
    await callback.answer()
    
    data = await state.get_data()
    answer_id = data.get("edit_answer_id")
    year = data.get("edit_answer_year")
    
    # Проверяем что ответ всё ещё можно редактировать
    answer = await get_answer_by_id(answer_id)
    if not answer or not is_editable(answer):
        await callback.message.answer(
            "⚠️ Время на редактирование истекло (прошло больше 24 часов)."
        )
        await state.clear()
        return
    
    await callback.message.answer(
        f"Напиши новый текст ответа за {year} год 👇"
    )
    
    await state.set_state(EditAnswerStates.waiting_for_new_text)


@router.message(EditAnswerStates.waiting_for_new_text)
async def process_new_text(message: Message, state: FSMContext):
    """Обработка нового текста ответа"""
    new_text = message.text.strip()
    
    if not new_text:
        await message.answer("Текст не может быть пустым. Попробуй ещё раз.")
        return
    
    data = await state.get_data()
    answer_id = data.get("edit_answer_id")
    year = data.get("edit_answer_year")
    
    # Финальная проверка времени
    answer = await get_answer_by_id(answer_id)
    if not answer or not is_editable(answer):
        await message.answer(
            "⚠️ Время на редактирование истекло (прошло больше 24 часов)."
        )
        await state.clear()
        return
    
    # Обновляем текст
    success = await update_answer_text(answer_id, new_text)
    
    if success:
        await message.answer(
            f"Ответ за {year} год обновлён ✅"
        )
    else:
        await message.answer(
            "Произошла ошибка при обновлении. Попробуй ещё раз."
        )
    
    await state.clear()


@router.callback_query(F.data == "edit_year")
async def edit_year_start(callback: CallbackQuery, state: FSMContext):
    """Начать изменение года ответа"""
    await callback.answer()
    
    data = await state.get_data()
    answer_id = data.get("edit_answer_id")
    
    # Проверяем что ответ всё ещё можно редактировать
    answer = await get_answer_by_id(answer_id)
    if not answer or not is_editable(answer):
        await callback.message.answer(
            "⚠️ Время на редактирование истекло (прошло больше 24 часов)."
        )
        await state.clear()
        return
    
    # Сохраняем режим выбора года
    await state.update_data(year_selection_mode="change_year")
    
    year_keyboard = get_year_keyboard()
    
    await callback.message.answer(
        "На какой год нужно заменить?\n\n"
        "Выбери год из списка или напиши год вручную:",
        parse_mode="HTML",
        reply_markup=year_keyboard
    )
    
    await state.set_state(EditAnswerStates.waiting_for_new_year)


@router.message(EditAnswerStates.waiting_for_new_year)
async def process_new_year(message: Message, state: FSMContext):
    """Обработка нового года для ответа (ручной ввод)"""
    year_text = message.text.strip()
    
    # Проверка что это число
    try:
        new_year = int(year_text)
    except ValueError:
        year_keyboard = get_year_keyboard()
        await message.answer(
            "Пожалуйста, выбери год из списка или введи год числом (2019-текущий):",
            parse_mode="HTML",
            reply_markup=year_keyboard
        )
        return
    
    data = await state.get_data()
    answer_id = data.get("edit_answer_id")
    date_key = data.get("date_key")
    old_year = data.get("edit_answer_year")
    
    # Финальная проверка времени
    answer = await get_answer_by_id(answer_id)
    if not answer or not is_editable(answer):
        await message.answer(
            "⚠️ Время на редактирование истекло (прошло больше 24 часов)."
        )
        await state.clear()
        return
    
    # Валидация года
    is_valid, error_msg = await validate_and_process_year(
        year=new_year,
        state=state,
        mode="change_year",
        message_or_callback=message,
        date_key=date_key,
        user_db_id=data.get("user_db_id"),
        question_id=data.get("question_id"),
        current_year=data.get("current_year", datetime.now().year)
    )
    
    if not is_valid:
        year_keyboard = get_year_keyboard()
        await message.answer(
            f"{error_msg}\n\nВыбери другой год:",
            reply_markup=year_keyboard
        )
        return
    
    # Обновляем год
    success = await update_answer_year(answer_id, new_year, date_key)
    
    if success:
        await message.answer(
            f"Год для этого ответа изменён с {old_year} на {new_year} ✅"
        )
    else:
        await message.answer(
            "Произошла ошибка при обновлении. Попробуй ещё раз."
        )
    
    await state.clear()

@router.callback_query(F.data == "delete_answer")
async def delete_answer_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления ответа"""
    await callback.answer()
    
    data = await state.get_data()
    answer_id = data.get("edit_answer_id")
    year = data.get("edit_answer_year")
    
    # Проверяем что ответ всё ещё можно удалить
    answer = await get_answer_by_id(answer_id)
    if not answer or not is_editable(answer):
        await callback.message.answer(
            "⚠️ Время на удаление истекло (прошло больше 24 часов)."
        )
        await state.clear()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗑 Да, удалить",
            callback_data="confirm_delete"
        )],
        [InlineKeyboardButton(
            text="⬅️ Отмена",
            callback_data="back_to_today"
        )]
    ])
    
    await callback.message.answer(
        f"Точно удалить ответ за {year} год?\n\n"
        f"<i>{answer.answer_text}</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )    


@router.callback_query(F.data == "confirm_delete")
async def delete_answer_execute(callback: CallbackQuery, state: FSMContext):
    """Выполнение удаления ответа"""
    await callback.answer()
    
    data = await state.get_data()
    answer_id = data.get("edit_answer_id")
    year = data.get("edit_answer_year")
    
    # Финальная проверка времени
    answer = await get_answer_by_id(answer_id)
    if not answer or not is_editable(answer):
        await callback.message.answer(
            "⚠️ Время на удаление истекло (прошло больше 24 часов)."
        )
        await state.clear()
        return
    
    # Удаляем ответ
    success = await delete_answer(answer_id)
    
    if success:
        await callback.message.answer(
            f"Ответ за {year} год удалён ❌"
        )
    else:
        await callback.message.answer(
            "Произошла ошибка при удалении. Попробуй ещё раз."
        )
    
    await state.clear()


@router.callback_query(F.data == "back_to_today")
async def back_to_today(callback: CallbackQuery, state: FSMContext):
    """Вернуться к сегодняшнему вопросу"""
    await callback.answer()
    await state.clear()
    
    # Создаём фейковое сообщение для повторного вызова show_daily_question
    await show_daily_question(callback.message, state)