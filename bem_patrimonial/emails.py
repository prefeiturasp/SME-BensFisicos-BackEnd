import pytz
from django.conf import settings
from config.utils import email_utils

local_timezone = pytz.timezone(settings.TIME_ZONE)


def envia_email_cadastro_nao_aprovado(status):
    object_url = '{}/bem_patrimonial/bempatrimonial/{}/change/'.format(settings.ADMIN_URL, status.bem_patrimonial.id)
    subject = '[Bens Físicos] Cadastro não aprovado'
    dict = {
        'subject': subject,
        'title': 'Olá!',
        'subtitle': '''O cadastro do Bem Patrimonial "{}" foi reprovado.
                       Acesse {} para realizar os ajustes necessários.
                       Mais detalhes abaixo.
                    '''.format(status.bem_patrimonial.__str__(), object_url),
        'body': status.observacao
    }
    email_utils.send_email_ctrl(
        subject,
        dict,
        'simple_message.html',
        status.bem_patrimonial.criado_por.email
    )
