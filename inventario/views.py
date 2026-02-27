from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404

from inventario.models import ConciliacaoUA


from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao


def _operador_pode_exportar(user, conciliacao):
    if not getattr(user, "is_operador_inventario", False) or getattr(
        user, "is_gestor_patrimonio", False
    ):
        return True
    ua_user_id = getattr(user, "unidade_administrativa_id", None)
    if not ua_user_id or conciliacao.unidade_administrativa_id != ua_user_id:
        return False
    return True


@login_required
def download_conciliacao_pdf(request, pk):
    """
    Exporta a Conciliação (Eventual ou Anual) em PDF.
    """
    user = request.user

    try:
        conciliacao = ConciliacaoUA.objects.select_related(
            "unidade_administrativa"
        ).get(pk=pk)
    except ConciliacaoUA.DoesNotExist:
        raise Http404("Conciliação não encontrada.")

    if not _operador_pode_exportar(user, conciliacao):
        raise PermissionDenied(
            "Operador só pode exportar conciliações da própria Unidade Administrativa."
        )

    pdf_buffer = gerar_pdf_conciliacao(conciliacao, usuario_gerador=request.user)

    numero = getattr(conciliacao, "numero_conciliacao", None) or str(conciliacao.pk)
    ano = None
    if hasattr(conciliacao, "vigencia") and conciliacao.vigencia:
        ano = conciliacao.vigencia
    elif hasattr(conciliacao, "ano_vigencia") and conciliacao.ano_vigencia:
        ano = conciliacao.ano_vigencia

    ua_codigo = ""
    if conciliacao.unidade_administrativa and hasattr(
        conciliacao.unidade_administrativa, "codigo"
    ):
        ua_codigo = str(conciliacao.unidade_administrativa.codigo)

    partes = ["CONCILIACAO", str(numero)]
    if ano:
        partes.append(str(ano))
    if ua_codigo:
        partes.append(f"UA{ua_codigo}")

    filename = "_".join(partes) + ".pdf"

    try:
        pdf_buffer.seek(0)
    except Exception:
        pass

    return FileResponse(
        pdf_buffer,
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )
