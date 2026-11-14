"""Basic SQLalchemy models.

Author: Maxi-online
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    'Basic class for SQLalchemy models.'

    def __repr__(self) -> str:
        """Return the string view of the model.

        :return: Reading line with class name and identifier.
        """

        model_id = getattr(self, "id", None)
        return f"<{self.__class__.__name__} id={model_id}>"
