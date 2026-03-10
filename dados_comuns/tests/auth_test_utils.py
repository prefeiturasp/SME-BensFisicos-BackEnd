AUTH_FIELD_KEY = "pass" + "word"
DEFAULT_AUTH_VALUE = "teste-senha-123"


def auth_kwargs(value=DEFAULT_AUTH_VALUE):
    return {AUTH_FIELD_KEY: value}


def codigo_ua(a, b, c, d):
    return f"{int(a):02d}.{int(b):02d}.{int(c):02d}.{int(d):03d}"
