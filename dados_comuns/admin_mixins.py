from django import forms


class UnsavedChangesAdminMixin:
    """Adiciona proteção de saída a formulários editáveis do Django Admin."""

    @property
    def media(self):
        return super().media + forms.Media(
            css={"all": ("admin/unsaved_changes.css",)},
            js=("admin/unsaved_changes.js",),
        )
