from django.conf import settings
from config.utils import email_utils


def envia_email_alerta_novo_agendamento():
    subject = '[Bens físicos] Novo agendamento'
    dict = {
        'subject': subject,
        'title': 'Olá!',
        'subtitle': ''' Foi agendada uma nova reunião de suporte ao cadastro de Bem Patrimonial.
                        Acesse {} para visualizar mais detalhes.
                    '''.format(settings.ADMIN_URL)
    }
    email_utils.send_email_ctrl(
        subject,
        dict,
        'simple_message.html',
        settings.DEFAULT_TO_EMAIL
    )
