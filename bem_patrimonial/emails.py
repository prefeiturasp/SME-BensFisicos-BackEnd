import pytz
from django.conf import settings
from config.utils import email_utils

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
