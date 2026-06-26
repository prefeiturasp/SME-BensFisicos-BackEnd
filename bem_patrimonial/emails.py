from django.conf import settings
from django.utils import timezone
from config.utils import email_utils
from usuario.models import Usuario

EMAIL_TEMPLATE_SIMPLE_MESSAGE = "simple_message.html"
URL_BAIXA_FISICA_CHANGE = "{}/bem_patrimonial/baixafisicabempatrimonial/{}/change/"


def envia_email_cadastro_nao_aprovado(status):
    object_url = "{}/bem_patrimonial/bempatrimonial/{}/change/".format(
        settings.ADMIN_URL, status.bem_patrimonial.id
    )
    subject = "[Bens Físicos] Cadastro não aprovado"
    email_context = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": """O cadastro do Bem Patrimonial "{}" foi reprovado.
                       Acesse {} para realizar os ajustes necessários.
                       Mais detalhes abaixo.
                    """.format(
            status.bem_patrimonial.__str__(), object_url
        ),
        "body": status.observacao,
    }
    email_utils.send_email_ctrl(
        subject,
        email_context,
        EMAIL_TEMPLATE_SIMPLE_MESSAGE,
        status.bem_patrimonial.criado_por.email,
    )


def envia_email_nova_solicitacao_movimentacao(movimentacao, emails):
    if not emails:
        return

    ua_destino = movimentacao.unidade_administrativa_destino

    ua_info = (
        f"{ua_destino.codigo} – {ua_destino.nome}"
        if ua_destino.codigo
        else ua_destino.nome
    )

    itens = movimentacao.itens.select_related("bem").all()

    bens_info = []

    for item in itens:
        bem = item.bem
        if not bem:
            continue

        identificador = (
            f"{bem.numero_patrimonial} – {bem.nome}"
            if bem.numero_patrimonial
            else bem.nome
        )
        bens_info.append(identificador)

    if not bens_info and movimentacao.bem_patrimonial:
        bem = movimentacao.bem_patrimonial
        identificador = (
            f"{bem.numero_patrimonial} – {bem.nome}"
            if bem.numero_patrimonial
            else bem.nome
        )
        bens_info.append(identificador)

    if not bens_info:
        return

    lista_bens_formatada = "\n".join(f"- {info}" for info in bens_info)

    subject = "[Bens Físicos] Movimentação recebida para aceite"

    dict_params = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": (
            f"A Unidade Administrativa {ua_info} recebeu a movimentação dos seguintes bens patrimoniais para aceite:\n\n"  # noqa: E501
            f"{lista_bens_formatada}\n\n"
            f"Acesse {settings.ADMIN_URL} para concluir a movimentação."
        ),
    }

    email_utils.send_email_ctrl(
        subject,
        dict_params,
        EMAIL_TEMPLATE_SIMPLE_MESSAGE,
        emails,
    )


def envia_email_solicitacao_movimentacao_aceita(bem_patrimonial, emails=[]):
    subject = "[Bens físicos] Sua solicitação de movimentação foi aceita."
    email_context = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": """A solicitação de movimentação do bem patrimonial {} foi aceita.
                       Acesse {} para visualizar mais detalhes.
                    """.format(
            bem_patrimonial.__str__(), settings.ADMIN_URL
        ),
    }
    email_utils.send_email_ctrl(
        subject, email_context, EMAIL_TEMPLATE_SIMPLE_MESSAGE, emails
    )


def envia_email_solicitacao_movimentacao_rejeitada(bem_patrimonial, emails=[]):
    subject = "[Bens físicos] Sua solicitação de movimentação foi rejeitada."
    email_context = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": """A solicitação de movimentação do bem patrimonial {} foi rejeitada.
                       Acesse {} para visualizar mais detalhes.
                    """.format(
            bem_patrimonial.__str__(), settings.ADMIN_URL
        ),
    }
    email_utils.send_email_ctrl(
        subject, email_context, EMAIL_TEMPLATE_SIMPLE_MESSAGE, emails
    )


def envia_email_solicitacao_movimentacao_cancelada(
    bem_patrimonial, cancelado_por, emails=[]
):
    subject = "[Bens físicos] Sua solicitação de movimentação foi cancelada."
    email_context = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": """A solicitação de movimentação do bem patrimonial {} foi cancelada por {}.
                       Acesse {} para visualizar mais detalhes.
                    """.format(
            bem_patrimonial.__str__(),
            cancelado_por.nome or cancelado_por.username,
            settings.ADMIN_URL,
        ),
    }
    email_utils.send_email_ctrl(
        subject, email_context, EMAIL_TEMPLATE_SIMPLE_MESSAGE, emails
    )


def _bens_info_de_movimentacao(mov, max_bens_por_mov):
    """Retorna lista de identificadores dos bens e total de itens."""
    itens_qs = mov.itens.select_related("bem").all()
    total_itens = itens_qs.count()
    itens = itens_qs[:max_bens_por_mov]
    bens_info = []
    for item in itens:
        bem = item.bem
        if not bem:
            continue
        identificador = (
            f"{bem.numero_patrimonial} – {bem.nome}"
            if bem.numero_patrimonial
            else bem.nome
        )
        bens_info.append(identificador)
    if not bens_info and mov.bem_patrimonial:
        bem = mov.bem_patrimonial
        identificador = (
            f"{bem.numero_patrimonial} – {bem.nome}"
            if bem.numero_patrimonial
            else bem.nome
        )
        bens_info.append(identificador)
    return bens_info, total_itens


def envia_email_movimentacoes_pendentes_aceite(
    unidade_destino,
    movimentacoes,
    emails,
    dias_minimo=7,
    dias_urgente=30,
    max_movimentacoes=5,
    max_bens_por_mov=3,
):
    if not emails or not movimentacoes:
        return

    ua_info = (
        f"{unidade_destino.codigo} – {unidade_destino.nome}"
        if getattr(unidade_destino, "codigo", None)
        else unidade_destino.nome
    )

    hoje = timezone.localdate()
    total_movimentacoes = len(movimentacoes)
    movimentacoes_info = []
    for mov in movimentacoes[:max_movimentacoes]:
        data_envio = timezone.localdate(mov.criado_em)
        dias_pendentes = (hoje - data_envio).days
        bens_info, total_itens = _bens_info_de_movimentacao(mov, max_bens_por_mov)
        movimentacoes_info.append(
            {
                "id": mov.pk,
                "ua_origem": str(mov.unidade_administrativa_origem),
                "data_envio": data_envio.strftime("%d/%m/%Y"),
                "dias_pendentes": dias_pendentes,
                "urgente": dias_pendentes > dias_urgente,
                "bens": bens_info,
                "bens_excedentes": max(0, total_itens - max_bens_por_mov),
            }
        )

    total_urgentes = sum(1 for m in movimentacoes_info if m["urgente"])
    pendentes_url = (
        f"{settings.ADMIN_URL}/bem_patrimonial/movimentacaobempatrimonial/?atrasada=1"
    )
    subject = "[Bens Físicos] Movimentações pendentes de aceite"
    dict_params = {
        "subject": subject,
        "title": "Movimentações pendentes de aceite",
        "ua_info": ua_info,
        "dias_minimo": dias_minimo,
        "dias_urgente": dias_urgente,
        "total": total_movimentacoes,
        "exibidas": len(movimentacoes_info),
        "mov_excedentes": max(0, total_movimentacoes - len(movimentacoes_info)),
        "total_urgentes": total_urgentes,
        "movimentacoes": movimentacoes_info,
        "pendentes_url": pendentes_url,
    }
    email_utils.send_email_ctrl(
        subject,
        dict_params,
        "movimentacoes_pendentes_aceite_email.html",
        emails,
    )


def _formata_lista_bens_baixa(baixa_fisica):
    """
    Monta uma lista de identificação dos bens associados à baixa física,
    para uso nos textos dos e-mails.
    """
    itens = baixa_fisica.itens.select_related("bem").all()
    bens_info = []

    for item in itens:
        bem = item.bem
        if not bem:
            continue

        identificador = (
            f"{bem.numero_patrimonial} – {bem.nome}"
            if bem.numero_patrimonial
            else bem.nome
        )
        bens_info.append(identificador)

    if not bens_info:
        return None

    return "\n".join(f"- {info}" for info in bens_info)


def envia_email_baixa_fisica_solicitada(baixa_fisica):
    """
    Envio de e-mail quando a baixa é solicitada (ação: acao_enviar_baixa).
    Destinatários: todos da unidade associada à baixa (unidade_administrativa_origem).
    """
    # gestores da UA de origem
    gestores = (
        Usuario.objects.filter(
            is_active=True,
            unidades_administrativas=baixa_fisica.unidade_administrativa_origem,
        )
        .distinct()
        .only("email")
    )

    emails = [u.email for u in gestores if u.email]
    if not emails:
        return

    object_url = URL_BAIXA_FISICA_CHANGE.format(settings.ADMIN_URL, baixa_fisica.id)

    ua = baixa_fisica.unidade_administrativa_origem
    ua_info = f"{ua.codigo} – {ua.nome}" if getattr(ua, "codigo", None) else ua.nome

    lista_bens_formatada = _formata_lista_bens_baixa(baixa_fisica) or ""

    subject = "[Bens Físicos] Baixa Física solicitada para aprovação"
    dict_params = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": (
            f"Foi registrada uma solicitação de Baixa Física na unidade administrativa {ua_info}.\n\n"
            f"Número do processo de Baixa Física: {baixa_fisica.numero_processo_baixa}\n\n"
            f"Bens envolvidos:\n{lista_bens_formatada}\n\n"
            f"Acesse {object_url} para analisar a solicitação."
        ),
    }

    email_utils.send_email_ctrl(
        subject,
        dict_params,
        EMAIL_TEMPLATE_SIMPLE_MESSAGE,
        emails,
    )


def envia_email_baixa_fisica_aprovada(baixa_fisica):
    """
    Envio de e-mail quando a baixa é aprovada (ação: acao_aprovar_baixa).
    Destinatário: usuário que criou a baixa (criado_por).
    """
    if not baixa_fisica.criado_por or not baixa_fisica.criado_por.email:
        return

    object_url = URL_BAIXA_FISICA_CHANGE.format(settings.ADMIN_URL, baixa_fisica.id)

    lista_bens_formatada = _formata_lista_bens_baixa(baixa_fisica) or ""

    subject = "[Bens Físicos] Sua Baixa Física foi aprovada"
    dict_params = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": (
            f"A solicitação de Baixa Física de número de processo {baixa_fisica.numero_processo_baixa} "
            f"foi aprovada.\n\n"
            f"Bens baixados:\n{lista_bens_formatada}\n\n"
            f"Acesse {object_url} para visualizar mais detalhes."
        ),
    }

    email_utils.send_email_ctrl(
        subject,
        dict_params,
        EMAIL_TEMPLATE_SIMPLE_MESSAGE,
        baixa_fisica.criado_por.email,
    )


def envia_email_baixa_fisica_cancelada(baixa_fisica, usuario_cancelador):
    """
    Envio de e-mail quando a baixa é cancelada (ação: acao_cancelar_baixa).
    Destinatário: usuário que criou a baixa (criado_por).
    """
    if not baixa_fisica.criado_por or not baixa_fisica.criado_por.email:
        return

    object_url = URL_BAIXA_FISICA_CHANGE.format(settings.ADMIN_URL, baixa_fisica.id)

    cancelador_nome = (
        usuario_cancelador.nome or usuario_cancelador.username
        if usuario_cancelador
        else "gestor responsável"
    )

    lista_bens_formatada = _formata_lista_bens_baixa(baixa_fisica) or ""

    subject = "[Bens Físicos] Sua Baixa Física foi cancelada"
    dict_params = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": (
            f"A solicitação de Baixa Física de número de processo {baixa_fisica.numero_processo_baixa} "
            f"foi cancelada por {cancelador_nome}.\n\n"
            f"Bens envolvidos:\n{lista_bens_formatada}\n\n"
            f"Acesse {object_url} para visualizar mais detalhes."
        ),
    }

    email_utils.send_email_ctrl(
        subject,
        dict_params,
        EMAIL_TEMPLATE_SIMPLE_MESSAGE,
        baixa_fisica.criado_por.email,
    )
