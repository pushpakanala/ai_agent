from typing import List

"""
    Add collections here
"""

__all__ = (
    "users",
    "email_history"
)


users="users"
email_history="email_history"


def __dir__() -> List[str]:
    return sorted(list(__all__))
