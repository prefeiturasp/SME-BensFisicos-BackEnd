import json

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from bem_patrimonial.models import MovimentacaoBemPatrimonial
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria

from dados_comuns.escopo import (
    filtrar_ua_origem_por_escopo,
)


CODIGO_UA_PONTO_CENTRAL = "001"
MENSAGEM_SEM_PONTO_CENTRAL = (
    "Não há ponto central cadastrado na Unidade Orçamentária de destino. "
    "Por favor, entrar em contato com o gestor"
)


def q_codigo_ponto_central():
    return Q(codigo=CODIGO_UA_PONTO_CENTRAL) | Q(
        codigo__endswith=f".{CODIGO_UA_PONTO_CENTRAL}"
    )


def serializar_ua_para_opcao(ua):
    return {"id": str(ua.pk), "label": str(ua)}


def obter_uo_referencia_do_usuario(usuario):
    if not usuario:
        return None

    unidade_orcamentaria = getattr(usuario, "unidade_orcamentaria", None)
    if unidade_orcamentaria:
        return unidade_orcamentaria

    unidade_administrativa = getattr(usuario, "unidade_administrativa", None)
    return getattr(unidade_administrativa, "unidade_orcamentaria", None)


def queryset_uos_destino():
    return UnidadeOrcamentaria.objects.filter(ativa=True).order_by("codigo", "nome")


def queryset_uas_ativas():
    return (
        UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA)
        .select_related("unidade_orcamentaria")
        .order_by("unidade_orcamentaria__codigo", "codigo", "sigla", "nome")
    )


def queryset_uas_da_uo(unidade_orcamentaria):
    qs = queryset_uas_ativas()
    if not unidade_orcamentaria:
        return qs.none()
    return qs.filter(unidade_orcamentaria=unidade_orcamentaria)


def obter_ua_ponto_central(unidade_orcamentaria):
    if not unidade_orcamentaria:
        return None

    return (
        queryset_uas_da_uo(unidade_orcamentaria)
        .filter(q_codigo_ponto_central())
        .order_by("id")
        .first()
    )


def montar_configuracao_destino_widget(usuario):
    uo_referencia = obter_uo_referencia_do_usuario(usuario)

    centrais_por_uo = {}
    uas_ponto_central = queryset_uas_ativas().filter(q_codigo_ponto_central())
    for ua in uas_ponto_central:
        centrais_por_uo[str(ua.unidade_orcamentaria_id)] = serializar_ua_para_opcao(ua)

    opcoes_mesma_uo = []
    if uo_referencia:
        opcoes_mesma_uo = [
            serializar_ua_para_opcao(ua) for ua in queryset_uas_da_uo(uo_referencia)
        ]

    return json.dumps(
        {
            "uoReferenciaId": str(uo_referencia.pk) if uo_referencia else "",
            "centraisPorUo": centrais_por_uo,
            "opcoesMesmaUo": opcoes_mesma_uo,
            "mensagemSemPontoCentral": MENSAGEM_SEM_PONTO_CENTRAL,
        }
    )


class MovimentacaoBemPatrimonialForm(forms.ModelForm):
    unidade_orcamentaria_destino = forms.ModelChoiceField(
        label="Unidade orçamentária de destino",
        queryset=queryset_uos_destino().none(),
        required=False,
    )

    class Meta:
        model = MovimentacaoBemPatrimonial
        fields = (
            "unidade_administrativa_origem",
            "unidade_orcamentaria_destino",
            "unidade_administrativa_destino",
            "observacao",
        )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if "unidade_administrativa_destino" in self.fields:
            self.fields["unidade_administrativa_destino"].required = False
            self.fields["unidade_administrativa_destino"].widget = forms.Select()
        self._configure_dynamic_fields()

    def _get_user(self):
        if getattr(self, "request", None) and getattr(self.request, "user", None):
            return self.request.user
        return None

    def _get_uo_referencia(self, user, ua_origem=None):
        uo_referencia = obter_uo_referencia_do_usuario(user)
        if uo_referencia:
            return uo_referencia
        return getattr(ua_origem, "unidade_orcamentaria", None)

    def _get_selected_ua_origem(self, queryset_ativas):
        if self.is_bound:
            ua_origem_id = self.data.get(self.add_prefix("unidade_administrativa_origem"))
            if ua_origem_id:
                return queryset_ativas.filter(pk=ua_origem_id).first()

        if self.instance.pk:
            return self.instance.unidade_administrativa_origem

        initial_value = self.fields["unidade_administrativa_origem"].initial
        if initial_value:
            return queryset_ativas.filter(pk=initial_value).first()

        return None

    def _get_selected_uo_destino(self, queryset_uos, uo_referencia):
        if self.is_bound:
            uo_destino_id = self.data.get(self.add_prefix("unidade_orcamentaria_destino"))
            if uo_destino_id:
                return queryset_uos.filter(pk=uo_destino_id).first()

        if self.instance.pk and self.instance.unidade_administrativa_destino_id:
            return self.instance.unidade_administrativa_destino.unidade_orcamentaria

        initial_value = self.fields["unidade_orcamentaria_destino"].initial
        if initial_value:
            return queryset_uos.filter(pk=initial_value).first()

        return uo_referencia

    def _set_initial_origem_para_usuario(self, user):
        ua_user = getattr(user, "unidade_administrativa", None)
        if (
            not self.instance.pk
            and "unidade_administrativa_origem" in self.fields
            and ua_user
            and ua_user.is_ativa
            and not self.fields["unidade_administrativa_origem"].initial
        ):
            self.fields["unidade_administrativa_origem"].initial = ua_user.pk

    def _set_initial_uo_destino(self, uo_referencia):
        if (
            not self.instance.pk
            and "unidade_orcamentaria_destino" in self.fields
            and uo_referencia
            and not self.fields["unidade_orcamentaria_destino"].initial
        ):
            self.fields["unidade_orcamentaria_destino"].initial = uo_referencia.pk

    def _configure_destino_field_for_change(self, campo_destino, qs_ativas):
        campo_destino.queryset = qs_ativas.filter(
            pk=self.instance.unidade_administrativa_destino_id
        )
        campo_destino.initial = self.instance.unidade_administrativa_destino_id
        campo_destino.disabled = True
        if "unidade_orcamentaria_destino" in self.fields:
            self.fields["unidade_orcamentaria_destino"].disabled = True

    def _configure_destino_field_for_create(
        self,
        campo_destino,
        qs_ativas,
        uo_destino,
        destino_mesma_uo,
    ):
        if uo_destino is None:
            campo_destino.queryset = qs_ativas
            campo_destino.disabled = False
            return

        if destino_mesma_uo:
            campo_destino.queryset = queryset_uas_da_uo(uo_destino)
            campo_destino.disabled = False
            return

        ua_ponto_central = obter_ua_ponto_central(uo_destino)
        if ua_ponto_central:
            campo_destino.queryset = qs_ativas.filter(pk=ua_ponto_central.pk)
            campo_destino.initial = ua_ponto_central.pk
        else:
            campo_destino.queryset = qs_ativas.none()
            campo_destino.initial = None

        campo_destino.disabled = True

    def _configure_dynamic_fields(self):
        user = self._get_user()
        qs_ativas = queryset_uas_ativas()
        qs_uos = queryset_uos_destino()
        possui_campo_origem = "unidade_administrativa_origem" in self.fields
        possui_campo_uo_destino = "unidade_orcamentaria_destino" in self.fields
        possui_campo_ua_destino = "unidade_administrativa_destino" in self.fields

        if possui_campo_uo_destino:
            self.fields["unidade_orcamentaria_destino"].queryset = qs_uos
            self.fields["unidade_orcamentaria_destino"].widget.attrs[
                "data-movimentacao-destino-config"
            ] = montar_configuracao_destino_widget(user)

        if possui_campo_origem:
            if user:
                self.fields["unidade_administrativa_origem"].queryset = (
                    filtrar_ua_origem_por_escopo(user, qs_ativas)
                )
            else:
                self.fields["unidade_administrativa_origem"].queryset = qs_ativas

        if possui_campo_origem:
            self._set_initial_origem_para_usuario(user)

        ua_origem = self._get_selected_ua_origem(qs_ativas)
        uo_referencia = self._get_uo_referencia(user, ua_origem)

        if possui_campo_uo_destino:
            self._set_initial_uo_destino(uo_referencia)

        uo_destino = self._get_selected_uo_destino(qs_uos, uo_referencia)
        destino_mesma_uo = (
            uo_destino is not None
            and uo_referencia is not None
            and uo_destino.pk == uo_referencia.pk
        )

        if not possui_campo_ua_destino:
            if self.instance.pk and possui_campo_uo_destino:
                self.fields["unidade_orcamentaria_destino"].disabled = True
            return

        campo_destino = self.fields["unidade_administrativa_destino"]

        if self.instance.pk:
            self._configure_destino_field_for_change(campo_destino, qs_ativas)
            return

        self._configure_destino_field_for_create(
            campo_destino,
            qs_ativas,
            uo_destino,
            destino_mesma_uo,
        )

    def _validate_ua_origem_destino_new(self, cleaned_data, user):
        ua_origem = cleaned_data.get("unidade_administrativa_origem")
        uo_destino = cleaned_data.get("unidade_orcamentaria_destino")

        if not ua_origem:
            raise ValidationError(
                {
                    "unidade_administrativa_origem": "Unidade administrativa de origem é obrigatória."
                }
            )

        uo_referencia = self._get_uo_referencia(user, ua_origem)
        if not uo_destino:
            uo_destino = uo_referencia
            cleaned_data["unidade_orcamentaria_destino"] = uo_destino

        if not uo_destino:
            raise ValidationError(
                {
                    "unidade_orcamentaria_destino": "Unidade Orçamentária de destino é obrigatória."
                }
            )

        if not getattr(uo_destino, "ativa", False):
            raise ValidationError(
                {
                    "unidade_orcamentaria_destino": "Unidade Orçamentária de destino está inativa."
                }
            )

        destino_mesma_uo = (
            uo_referencia is not None and uo_destino.pk == uo_referencia.pk
        )

        ua_destino = cleaned_data.get("unidade_administrativa_destino")
        if not destino_mesma_uo:
            ua_destino = obter_ua_ponto_central(uo_destino)
            if not ua_destino:
                raise ValidationError(
                    {
                        "unidade_orcamentaria_destino": MENSAGEM_SEM_PONTO_CENTRAL
                    }
                )
            cleaned_data["unidade_administrativa_destino"] = ua_destino

        if not ua_destino:
            raise ValidationError(
                {
                    "unidade_administrativa_destino": "Unidade administrativa de destino é obrigatória."
                }
            )
        if not ua_origem.is_ativa:
            raise ValidationError(
                {
                    "unidade_administrativa_origem": (
                        f"A unidade de origem '{ua_origem.nome}' está inativa. "
                        "Não é possível criar movimentações a partir de unidades inativas."
                    )
                }
            )
        if not ua_destino.is_ativa:
            raise ValidationError(
                {
                    "unidade_administrativa_destino": (
                        f"A unidade de destino '{ua_destino.nome}' está inativa. "
                        "Não é possível criar movimentações para unidades inativas."
                    )
                }
            )
        if ua_destino == ua_origem:
            raise ValidationError(
                "Operação não permitida: origem e destino são iguais."
            )

        if ua_destino.unidade_orcamentaria_id != uo_destino.id:
            raise ValidationError(
                {
                    "unidade_administrativa_destino": (
                        "A Unidade Administrativa de destino não pertence à Unidade "
                        "Orçamentária selecionada."
                    )
                }
            )

        if not user:
            return

        qs_origem = filtrar_ua_origem_por_escopo(
            user, UnidadeAdministrativa.objects.all()
        )
        if not qs_origem.filter(pk=ua_origem.pk).exists():
            raise ValidationError(
                {
                    "unidade_administrativa_origem": "UA de origem fora do seu escopo de acesso."
                }
            )

        if destino_mesma_uo:
            qs_destino = queryset_uas_da_uo(uo_referencia)
            if not qs_destino.filter(pk=ua_destino.pk).exists():
                raise ValidationError(
                    {
                        "unidade_administrativa_destino": (
                            "UA de destino fora das UAs permitidas para sua UO."
                        )
                    }
                )

        qs_uos = queryset_uos_destino()
        if not qs_uos.filter(pk=uo_destino.pk).exists():
            raise ValidationError(
                {
                    "unidade_orcamentaria_destino": "UO de destino fora das opções disponíveis."
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        user = self._get_user()
        is_editing = self.instance.pk is not None
        if not is_editing:
            self._validate_ua_origem_destino_new(cleaned_data, user)
        elif self.instance.unidade_administrativa_destino_id:
            cleaned_data["unidade_orcamentaria_destino"] = (
                self.instance.unidade_administrativa_destino.unidade_orcamentaria
            )
        if is_editing and user and getattr(user, "is_operador_inventario", False):
            if self.instance.solicitado_por_id != user.id:
                raise ValidationError(
                    "Não é permitido alterar uma movimentação solicitada por outro usuário."
                )
        return cleaned_data
