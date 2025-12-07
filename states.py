from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    """Состояния для онбординга нового пользователя"""
    waiting_for_time = State()


class QuestionStates(StatesGroup):
    """Состояния для работы с вопросами и ответами"""
    waiting_for_question = State()
    waiting_for_answer = State()

class PastYearsStates(StatesGroup):
    """Состояния для ввода ответов за прошлые годы"""
    waiting_for_year = State()
    waiting_for_past_answer = State()

class SettingsStates(StatesGroup):
    """Состояния для настроек"""
    waiting_for_new_time = State()

class EditAnswerStates(StatesGroup):
    """Состояния для редактирования/удаления ответов"""
    waiting_for_year_to_edit = State()
    waiting_for_new_text = State()
    waiting_for_new_year = State()
    confirm_delete = State()


class DateViewStates(StatesGroup):
    """Состояния для просмотра записей по конкретной дате"""
    waiting_for_date = State()


class BackdatedEntryStates(StatesGroup):
    """Состояния для создания записей задним числом через /date"""
    waiting_for_backdated_question = State()
    waiting_for_backdated_answer = State()


class EveningReminderStates(StatesGroup):
    """Состояния для вечернего напоминания в 23:00"""
    waiting_for_evening_answer = State()
    waiting_for_evening_question = State()
    waiting_for_evening_answer_after_question = State()