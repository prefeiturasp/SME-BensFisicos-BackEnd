from django.db import models


def repr_value(value):
    if value is None:
        return ""
    if isinstance(value, models.Model):
        pk = getattr(value, "pk", None)
        try:
            return f"{pk} - {str(value)}"
        except Exception:
            return str(value)
    return str(value)


def dict_changes(original, updated, fields, only=None, ignore=None):
    """Retorna dict {field: (old_str, new_str)} para campos alterados."""
    ignore = set(ignore or [])
    if only is not None:
        fields = [f for f in fields if f in set(only)]

    changes = {}
    for f in fields:
        if f in ignore:
            continue
        old = getattr(original, f, None)
        new = getattr(updated, f, None)
        if repr_value(old) != repr_value(new):
            changes[f] = (repr_value(old), repr_value(new))
    return changes
