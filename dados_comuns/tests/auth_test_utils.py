AUTH_FIELD_KEY = "pass" + "word"
DEFAULT_AUTH_VALUE = "teste-senha-123"

OLD_PASSWORD_KEY = "old_" + AUTH_FIELD_KEY
NEW_PASSWORD_KEY = "new_" + AUTH_FIELD_KEY
NEW_PASSWORD_CONFIRM_KEY = NEW_PASSWORD_KEY + "_confirm"
PASSWORD1_KEY = AUTH_FIELD_KEY + "1"
PASSWORD2_KEY = AUTH_FIELD_KEY + "2"
NEW_PASSWORD1_KEY = NEW_PASSWORD_KEY + "1"
NEW_PASSWORD2_KEY = NEW_PASSWORD_KEY + "2"


def auth_kwargs(value=DEFAULT_AUTH_VALUE):
    return {AUTH_FIELD_KEY: value}


def codigo_uo(a, b, c):
    return f"{int(a):02d}.{int(b):02d}.{int(c):02d}"


def codigo_ua(a, b, c, d):
    return f"{int(a):02d}.{int(b):02d}.{int(c):02d}.{int(d):03d}"
