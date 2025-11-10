from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from bem_patrimonial.models import MovimentacaoBemPatrimonial


@login_required
def download_documento_cimbpm(request, pk):
    movimentacao = get_object_or_404(MovimentacaoBemPatrimonial, pk=pk)

    if not movimentacao.documento_cimbpm:
        raise Http404("Documento CIMBPM não encontrado")

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

    if not movimentacao.documento_existe():
        try:
            movimentacao.regenerar_documento_cimbpm(force=True)
            movimentacao.refresh_from_db()
        except Exception as e:
            raise Http404(f"Erro ao gerar documento: {str(e)}")

    filename = f"CIMBPM_{movimentacao.numero_cimbpm.replace('.', '_')}.pdf"

    response = FileResponse(
        movimentacao.documento_cimbpm.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )

    return response
