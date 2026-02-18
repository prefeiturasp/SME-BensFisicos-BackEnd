import re
import string
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PasswordComplexityValidator:

    def validate(self, password, user=None):
        errors = []

        if not re.search(r"[a-zA-Z]", password):
            errors.append(
                ValidationError(
                    _("Sua senha deve conter pelo menos uma letra."),
                    code="password_no_letter",
                )
            )

        if not re.search(r"\d", password):
            errors.append(
                ValidationError(
                    _("Sua senha deve conter pelo menos um número."),
                    code="password_no_digit",
                )
            )

        if not any(char in string.punctuation for char in password):
            errors.append(
                ValidationError(
                    _("Sua senha deve conter pelo menos um caractere especial."),
                    code="password_no_special_char",
                )
            )

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _("Sua senha deve conter letras, números e caracteres especiais.")
