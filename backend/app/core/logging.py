"""Настройка логирования.

Автор: Maxi-online
"""

import logging


def configure_logging(level: str) -> None:
    """Настроить корневой логгер приложения.

    :param level: Уровень логирования (например, "INFO", "DEBUG").
    :return: None. Функция настраивает логирование глобально.
    """

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
