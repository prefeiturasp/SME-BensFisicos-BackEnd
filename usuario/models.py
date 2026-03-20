from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

from dados_comuns.models import UnidadeOrcamentaria, UnidadeAdministrativa
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class Usuario(AbstractUser):
    nome = models.CharField("Nome", max_length=255, null=True, blank=False)  # NOSONAR
    rf = models.CharField(
        "RF",
        max_length=20,
        null=True,  # NOSONAR
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z][0-9]+$",
                message="RF deve começar com uma letra e conter apenas números após ela. Ex: F53399 ou f53399.",
            )
        ],
    )
    unidade_orcamentaria = models.ForeignKey(
        UnidadeOrcamentaria,
        verbose_name="Unidade Orçamentária",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
    )
    unidade_administrativa = models.ForeignKey(
        UnidadeAdministrativa,
        related_name="%(class)s_unidade_administrativa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    unidades_administrativas = models.ManyToManyField(
        UnidadeAdministrativa,
        related_name="operadores",
        blank=True,
        verbose_name="Unidades Administrativas permitidas",
    )
    must_change_password = models.BooleanField(default=True)
    last_password_change = models.DateTimeField(null=True, blank=True)

    def clean(self):
        super().clean()

        if self.unidade_administrativa and not self.unidade_orcamentaria:
            raise ValidationError(
                {
                    "unidade_orcamentaria": "Informe a Unidade Orçamentária antes de definir a Unidade Administrativa."
                }
            )

        if (
            self.unidade_orcamentaria
            and self.unidade_administrativa
            and self.unidade_administrativa.unidade_orcamentaria_id
            != self.unidade_orcamentaria_id
        ):
            raise ValidationError(
                {
                    "unidade_administrativa": "A Unidade Administrativa deve pertencer à Unidade Orçamentária selecionada."  # noqa: E501
                }
            )

    @property
    def is_gestor_patrimonio(self):
        return self.groups.filter(name=GRUPO_GESTOR_PATRIMONIO).exists()

    @property
    def is_operador_inventario(self):
        return self.groups.filter(name=GRUPO_OPERADOR_INVENTARIO).exists()

    @property
    def uas_permitidas(self):
        if self.is_superuser:
            return UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
        if self.is_gestor_patrimonio:
            uo_id = self.unidade_orcamentaria_id
            if uo_id:
                return UnidadeAdministrativa.objects.filter(
                    unidade_orcamentaria_id=uo_id, status=UnidadeAdministrativa.ATIVA
                )
        return self.unidades_administrativas.all()
