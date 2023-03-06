from django.db.models.signals import post_save
from django.dispatch import receiver
from bem_patrimonial.models import BemPatrimonial, AGUARDANDO_APROVACAO


@receiver(post_save, sender=BemPatrimonial)
def cria_primeiro_historico_status(sender, instance, created, **kwargs):
    if created:
        instance.bempatrimonial_historicostatusbempatrimonial_set.create(
            status=AGUARDANDO_APROVACAO,
            atualizado_por=instance.criado_por
        )
