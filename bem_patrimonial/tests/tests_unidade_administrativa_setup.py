import datetime

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.constants import APROVADO

from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO
from django.contrib.auth.models import Group


class SetupUnidadeAdministrativaStatusData:

    def create_unidades_administrativas(self):
        ua_ativa_1 = UnidadeAdministrativa.objects.create(
            nome="DRE Centro Ativa",
            codigo="DRE-CENTRO",
            sigla="DREC",
            status=UnidadeAdministrativa.ATIVA,
        )
        ua_ativa_2 = UnidadeAdministrativa.objects.create(
            nome="DRE Sul Ativa",
            codigo="DRE-SUL",
            sigla="DRES",
            status=UnidadeAdministrativa.ATIVA,
        )
        ua_inativa = UnidadeAdministrativa.objects.create(
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

    def create_bem_patrimonial(self, criado_por, ua_origem, quantidade=10):
        bem = BemPatrimonial.objects.create(
            nome="Notebook Dell",
            data_compra_entrega=datetime.date.today(),
            origem="aquisicao_direta",
            marca="Dell",
            modelo="Inspiron 15",
            quantidade=quantidade,
            descricao="Notebook Dell Inspiron 15",
            valor_unitario=3500.00,
            numero_processo=123456,
            autorizacao_no_doc_em=datetime.date.today(),
            numero_nibpm=111111,
            numero_cimbpm=222222,
            localizacao="Almoxarifado",
            criado_por=criado_por,
            status=APROVADO,
        )

        return bem
