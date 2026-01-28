from datetime import timedelta

from django import template
from django.urls import reverse
from django.utils import timezone

from bem_patrimonial import constants
from bem_patrimonial.models import MovimentacaoBemPatrimonial

register = template.Library()


@register.inclusion_tag("admin/alerta_movimentacoes_pendentes.html", takes_context=True)
def alerta_movimentacoes_pendentes(context, css_class=""):
    request = context.get("request")
    if not request or not getattr(request, "user", None):
        return {"pendencias": None, "css_class": css_class}

    user = request.user
    if not user.is_authenticated:
        return {"pendencias": None, "css_class": css_class}

    ua = getattr(user, "unidade_administrativa", None)
    if not ua:
        return {"pendencias": None, "css_class": css_class}

    if not (
        user.is_gestor_patrimonio or user.is_operador_inventario or user.is_superuser
    ):
        return {"pendencias": None, "css_class": css_class}

    limite = timezone.now() - timedelta(days=7)
    qs = MovimentacaoBemPatrimonial.objects.filter(
        status=constants.ENVIADA,
        unidade_administrativa_destino=ua,
        criado_em__lte=limite,
    )

    total = qs.count()
    if total == 0:
        return {"pendencias": None, "css_class": css_class}

    url = (
        reverse("admin:bem_patrimonial_movimentacaobempatrimonial_changelist")
        + "?atrasada=1"
    )

    return {
        "pendencias": {
            "total": total,
            "url": url,
        },
        "css_class": css_class,
    }
