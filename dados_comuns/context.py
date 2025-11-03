import threading

_local = threading.local()


def set_user(user):
    _local.user = user


def get_user():
    return getattr(_local, "user", None)


from contextlib import contextmanager


@contextmanager
def audit_as(user):
    prev = get_user()
    try:
        set_user(user)
        yield
    finally:
        set_user(prev)
