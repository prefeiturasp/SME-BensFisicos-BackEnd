from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from dados_comuns.models import UnidadeAdministrativa


class Usuario(AbstractUser):
    nome = models.CharField("Nome", max_length=255, null=True, blank=False)
    unidade_administrativa = models.ForeignKey(UnidadeAdministrativa, on_delete=models.SET_NULL,
                                               null=True, blank=True)
