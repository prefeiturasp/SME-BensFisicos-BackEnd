from rest_framework import serializers
from agendamento_suporte.models import ConfigAgendaSuporte


class ConfigAgendaSuporteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigAgendaSuporte
        fields = '__all__'
