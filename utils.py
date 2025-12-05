from datetime import datetime, timedelta
from database.models import Answer
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def is_editable(answer: Answer) -> bool:
    """
    Проверяет, можно ли редактировать ответ (прошло ли меньше 24 часов с создания)
    
    Args:
        answer: Объект Answer из БД
        
    Returns:
        True если ответ можно редактировать, False если прошло больше 24 часов
    """
    if not answer or not answer.created_at:
        return False
    
    now = datetime.utcnow()
    time_passed = now - answer.created_at
    
    return time_passed <= timedelta(hours=24)


def get_time_left_str(answer: Answer) -> str:
    """
    Возвращает строку с оставшимся временем для редактирования
    
    Args:
        answer: Объект Answer из БД
        
    Returns:
        Строка вида "осталось 5 часов" или "время истекло"
    """
    if not answer or not answer.created_at:
        return "неизвестно"
    
    now = datetime.utcnow()
    deadline = answer.created_at + timedelta(hours=24)
    time_left = deadline - now
    
    if time_left.total_seconds() <= 0:
        return "время истекло"
    
    hours = int(time_left.total_seconds() // 3600)
    
    if hours >= 1:
        return f"осталось {hours} ч."
    else:
        minutes = int(time_left.total_seconds() // 60)
        return f"осталось {minutes} мин."
    
def is_leap_year(year: int) -> bool:
    """
    Проверяет, является ли год високосным

    Правило: год високосный если делится на 400, или делится на 4 и не делится на 100
    Примеры: 2000 (високосный), 2024 (високосный), 1900 (не високосный), 2100 (не високосный)

    Args:
        year: Год для проверки

    Returns:
        True если год високосный, False иначе
    """
    return (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)


def get_year_keyboard(start_year: int = 2019, buttons_per_row: int = 3) -> InlineKeyboardMarkup:
    """
    Создаёт inline-клавиатуру с кнопками годов от start_year до текущего года
    
    Args:
        start_year: Начальный год (по умолчанию 2019)
        buttons_per_row: Количество кнопок в ряду (по умолчанию 3)
        
    Returns:
        InlineKeyboardMarkup с кнопками годов
    """
    current_year = datetime.now().year
    years = list(range(start_year, current_year + 1))
    
    buttons = []
    for i in range(0, len(years), buttons_per_row):
        row = years[i:i + buttons_per_row]
        buttons.append([
            InlineKeyboardButton(
                text=str(year),
                callback_data=f"select_year:{year}"
            )
            for year in row
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)    