from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from bem_patrimonial.models import MovimentacaoBemPatrimonial


@login_required
def download_documento_cimbpm(request, pk):
    movimentacao = get_object_or_404(MovimentacaoBemPatrimonial, pk=pk)

    if request.user.is_operador_inventario and not request.user.is_gestor_patrimonio:
        user_ua = request.user.unidade_administrativa

        if (
            movimentacao.unidade_administrativa_origem != user_ua
            and movimentacao.unidade_administrativa_destino != user_ua
        ):
            raise PermissionDenied(
                "Você não tem permissão para acessar este documento. "
                "Operadores só podem baixar documentos de movimentações "
                "relacionadas à sua Unidade Administrativa."
            )

    if not movimentacao.numero_cimbpm:
        raise Http404("Erro: Número CIMBPM não foi gerado para esta movimentação")

    from bem_patrimonial.cimbpm import gerar_pdf_cimbpm
    from django.utils import timezone

    data_aceite = None
    if movimentacao.aceita and movimentacao.aprovado_por:
        data_aceite = movimentacao.atualizado_em

    try:
        pdf_buffer = gerar_pdf_cimbpm(
            movimentacao,
            data_aceite=data_aceite,
            usuario_gerador=request.user,
            data_geracao=timezone.now(),
        )
    except Exception as e:
        raise Http404(f"Erro ao gerar documento: {str(e)}")

    filename = f"CIMBPM_{movimentacao.numero_cimbpm.replace('.', '_')}.pdf"

    response = FileResponse(
        pdf_buffer,
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )

    return response
