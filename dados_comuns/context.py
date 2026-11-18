import threading
from contextlib import contextmanager

_local = threading.local()


def set_user(user):
    _local.user = user


def get_user():
    user = getattr(_local, "user", None)
    if user is not None and getattr(user, "is_anonymous", False):
        return None
    return user


@contextmanager
def audit_as(user):
    prev = get_user()
    try:
        set_user(user)
        yield
    finally:
        set_user(prev)
