import pytz
from django.conf import settings
from config.utils import email_utils
from usuario.models import Usuario

local_timezone = pytz.timezone(settings.TIME_ZONE)


def envia_email_cadastro_nao_aprovado(status):
    object_url = "{}/bem_patrimonial/bempatrimonial/{}/change/".format(
        settings.ADMIN_URL, status.bem_patrimonial.id
    )
    subject = "[Bens Físicos] Cadastro não aprovado"
    dict = {
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
        subject, dict, "simple_message.html", status.bem_patrimonial.criado_por.email
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
            f"A Unidade Administrativa {ua_info} recebeu a movimentação dos seguintes bens patrimoniais para aceite:\n\n"
            f"{lista_bens_formatada}\n\n"
            f"Acesse {settings.ADMIN_URL} para concluir a movimentação."
        ),
    }

    email_utils.send_email_ctrl(
        subject,
        dict_params,
        "simple_message.html",
        emails,
    )


def envia_email_solicitacao_movimentacao_aceita(bem_patrimonial, emails=[]):
    subject = "[Bens físicos] Sua solicitação de movimentação foi aceita."
    dict = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": """A solicitação de movimentação do bem patrimonial {} foi aceita.
                       Acesse {} para visualizar mais detalhes.
                    """.format(
            bem_patrimonial.__str__(), settings.ADMIN_URL
        ),
    }
    email_utils.send_email_ctrl(subject, dict, "simple_message.html", emails)


def envia_email_solicitacao_movimentacao_rejeitada(bem_patrimonial, emails=[]):
    subject = "[Bens físicos] Sua solicitação de movimentação foi rejeitada."
    dict = {
        "subject": subject,
        "title": "Olá!",
        "subtitle": """A solicitação de movimentação do bem patrimonial {} foi rejeitada.
                       Acesse {} para visualizar mais detalhes.
                    """.format(
            bem_patrimonial.__str__(), settings.ADMIN_URL
        ),
    }
    email_utils.send_email_ctrl(subject, dict, "simple_message.html", emails)


def envia_email_solicitacao_movimentacao_cancelada(
    bem_patrimonial, cancelado_por, emails=[]
):
    subject = "[Bens físicos] Sua solicitação de movimentação foi cancelada."
    dict = {
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
    email_utils.send_email_ctrl(subject, dict, "simple_message.html", emails)


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
    gestores = Usuario.objects.filter(
        is_active=True,
        unidade_administrativa=baixa_fisica.unidade_administrativa_origem
    ).only("email")

    emails = [u.email for u in gestores if u.email]
    if not emails:
        return

    object_url = "{}/bem_patrimonial/baixafisicabempatrimonial/{}/change/".format(
        settings.ADMIN_URL, baixa_fisica.id
    )

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
        "simple_message.html",
        emails,
    )


def envia_email_baixa_fisica_aprovada(baixa_fisica):
    """
    Envio de e-mail quando a baixa é aprovada (ação: acao_aprovar_baixa).
    Destinatário: usuário que criou a baixa (criado_por).
    """
    if not baixa_fisica.criado_por or not baixa_fisica.criado_por.email:
        return

    object_url = "{}/bem_patrimonial/baixafisicabempatrimonial/{}/change/".format(
        settings.ADMIN_URL, baixa_fisica.id
    )

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
        "simple_message.html",
        baixa_fisica.criado_por.email,
    )


def envia_email_baixa_fisica_cancelada(baixa_fisica, usuario_cancelador):
    """
    Envio de e-mail quando a baixa é cancelada (ação: acao_cancelar_baixa).
    Destinatário: usuário que criou a baixa (criado_por).
    """
    if not baixa_fisica.criado_por or not baixa_fisica.criado_por.email:
        return

    object_url = "{}/bem_patrimonial/baixafisicabempatrimonial/{}/change/".format(
        settings.ADMIN_URL, baixa_fisica.id
    )

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
        "simple_message.html",
        baixa_fisica.criado_por.email,
    )
