import datetime
from django.test import TestCase

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.constants import APROVADO

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO
from django.contrib.auth.models import Group


class SetupUnidadeAdministrativaStatusData(TestCase):

    def create_unidades_administrativas(self):
        ua_ativa_1 = criar_ua(
            nome="DRE Centro Ativa",
            codigo="DRE-CENTRO",
            sigla="DREC",
            status=UnidadeAdministrativa.ATIVA,
        )
        ua_ativa_2 = criar_ua(
            uo=ua_ativa_1.unidade_orcamentaria,
            nome="DRE Sul Ativa",
            codigo="DRE-SUL",
            sigla="DRES",
            status=UnidadeAdministrativa.ATIVA,
        )
        ua_inativa = criar_ua(
            uo=ua_ativa_1.unidade_orcamentaria,
            nome="DRE Norte Inativa",
            codigo="DRE-NORTE",
            sigla="DREN",
            status=UnidadeAdministrativa.INATIVA,
        )
        return ua_ativa_1, ua_ativa_2, ua_inativa

    def create_usuarios(self, ua_ativa_1, ua_ativa_2):
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        operador_1 = Usuario.objects.create_user(
            username="operador1",
            email="operador1@test.com",
            password="test123",
            unidade_administrativa=ua_ativa_1,
        )
        operador_1.groups.add(grupo_operador)

        operador_2 = Usuario.objects.create_user(
            username="operador2",
            email="operador2@test.com",
            password="test123",
            unidade_administrativa=ua_ativa_2,
        )
        operador_2.groups.add(grupo_operador)

        gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            password="test123",
            is_staff=True,
            is_superuser=True,
            unidade_administrativa=ua_ativa_1,
        )
        gestor.groups.add(grupo_gestor)

        return operador_1, operador_2, gestor

    def create_bem_patrimonial(self, criado_por, ua_origem):
        """
        Agora os bens são sempre associados via inline.
        Neste método só criamos o bem aprovado.
        A geração automática do número acontece no save().
        """
        bem = BemPatrimonial.objects.create(
            nome="Notebook Dell",
            descricao="Notebook Dell Inspiron 15",
            valor_unitario=3500.00,
            marca="Dell",
            modelo="Inspiron 15",
            numero_processo="PROC-123456",
            sem_numeracao=True,  # gerará SEM-NUMERO-x
            numero_formato_antigo=False,
            localizacao="Almoxarifado",
            criado_por=criado_por,
            unidade_administrativa=ua_origem,
            status=APROVADO,
        )
        return bem
