from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

from dados_comuns.models import UnidadeAdministrativa
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class Usuario(AbstractUser):
    nome = models.CharField("Nome", max_length=255, null=True, blank=False)
    rf = models.CharField(
        "RF",
        max_length=20,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z][0-9]+$",
                message="RF deve começar com uma letra e conter apenas números após ela. Ex: F53399 ou f53399."
            )
        ],
    )
    unidade_administrativa = models.ForeignKey(
        UnidadeAdministrativa,
        related_name="%(class)s_unidade_administrativa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    must_change_password = models.BooleanField(default=True)
    last_password_change = models.DateTimeField(null=True, blank=True)

    @property
    def is_gestor_patrimonio(self):
        return self.groups.filter(name=GRUPO_GESTOR_PATRIMONIO).exists()

    @property
    def is_operador_inventario(self):
        return self.groups.filter(name=GRUPO_OPERADOR_INVENTARIO).exists()
