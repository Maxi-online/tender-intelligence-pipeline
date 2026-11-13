"""Базовые модели SQLAlchemy.

Автор: Maxi-online
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для моделей SQLAlchemy."""

    def __repr__(self) -> str:
        """Вернуть строковое представление модели.

        :return: Читаемая строка с названием класса и идентификатором.
        """

        model_id = getattr(self, "id", None)
        return f"<{self.__class__.__name__} id={model_id}>"
