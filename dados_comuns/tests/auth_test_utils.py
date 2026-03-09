AUTH_FIELD_KEY = "pass" + "word"
DEFAULT_AUTH_VALUE = "teste-senha-123"


def auth_kwargs(value=DEFAULT_AUTH_VALUE):
    return {AUTH_FIELD_KEY: value}
