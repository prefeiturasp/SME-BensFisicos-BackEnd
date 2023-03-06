from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from dados_comuns.models import UnidadeAdministrativa
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class Usuario(AbstractUser):
    nome = models.CharField("Nome", max_length=255, null=True, blank=False)
    unidade_administrativa = models.ForeignKey(UnidadeAdministrativa, on_delete=models.SET_NULL,
                                               null=True, blank=True)

    @property
    def is_gestor_patrimonio(self):
        return self.groups.filter(name=GRUPO_GESTOR_PATRIMONIO).exists()

    @property
    def is_operador_inventario(self):
        return self.groups.filter(name=GRUPO_OPERADOR_INVENTARIO).exists()
