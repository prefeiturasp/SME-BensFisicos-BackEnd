from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BemPatrimonial
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from inventario import constants
from inventario.models import ConciliacaoUA
from usuario.constants import (
    GRUPO_GESTOR_PATRIMONIO,
    GRUPO_OPERADOR_INVENTARIO,
)
from usuario.models import Usuario


class ConciliacaoAPIBaseTestCase(APITestCase):
    """
    Base compartilhada para os testes de API de Conciliação e Itens.

    Cria a estrutura organizacional (UO/UA), os grupos e os usuários padrão
    (gestor_com_ua, gestor_sem_ua, operador, operador_fora, superuser) uma
    única vez por classe de teste.

    Subclasses podem sobrescrever `username_prefix` para evitar conflito de
    unique constraints quando a classe base for reutilizada em outros
    arquivos de teste.
    """

    username_prefix = ""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._criar_estrutura_organizacional()
        cls._criar_grupos()
        cls._criar_usuarios()

    @classmethod
    def _criar_estrutura_organizacional(cls):
        cls.uo1 = criar_uo(
            codigo=codigo_uo(10, 10, 10), nome="UO 1", sigla="UO1"
        )
        cls.uo2 = criar_uo(
            codigo=codigo_uo(20, 20, 20), nome="UO 2", sigla="UO2"
        )
        cls.ua1 = criar_ua(
            uo=cls.uo1,
            codigo=codigo_ua(10, 10, 10, 1),
            sigla="UA1",
            nome="Unidade 1",
        )
        cls.ua2 = criar_ua(
            uo=cls.uo1,
            codigo=codigo_ua(10, 10, 10, 2),
            sigla="UA2",
            nome="Unidade 2",
        )
        cls.ua_fora = criar_ua(
            uo=cls.uo2,
            codigo=codigo_ua(20, 20, 20, 1),
            sigla="UAF",
            nome="Unidade Fora",
        )

    @classmethod
    def _criar_grupos(cls):
        cls.grupo_gestor = Group.objects.get_or_create(
            name=GRUPO_GESTOR_PATRIMONIO
        )[0]
        cls.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

    @classmethod
    def _criar_usuario(cls, *, username, email, nome, grupo, **kwargs):
        user = Usuario.objects.create_user(
            username=username,
            email=email,
            **auth_kwargs("test123"),
            nome=nome,
            is_staff=True,
            **kwargs,
        )
        user.groups.add(grupo)
        return user

    @classmethod
    def _criar_usuarios(cls):
        prefix = cls.username_prefix
        cls.gestor_com_ua = cls._criar_usuario(
            username=f"{prefix}gestor_com_ua",
            email=f"{prefix}gestor.com.ua@test.com",
            nome="Gestor Com UA",
            grupo=cls.grupo_gestor,
            unidade_administrativa=cls.ua1,
            unidade_orcamentaria=cls.uo1,
        )
        cls.gestor_sem_ua = cls._criar_usuario(
            username=f"{prefix}gestor_sem_ua",
            email=f"{prefix}gestor.sem.ua@test.com",
            nome="Gestor Sem UA",
            grupo=cls.grupo_gestor,
            unidade_orcamentaria=cls.uo1,
        )
        cls.operador = cls._criar_usuario(
            username=f"{prefix}operador",
            email=f"{prefix}operador@test.com",
            nome="Operador",
            grupo=cls.grupo_operador,
            unidade_administrativa=cls.ua1,
            unidade_orcamentaria=cls.uo1,
        )
        cls.operador_fora = cls._criar_usuario(
            username=f"{prefix}operador_fora",
            email=f"{prefix}operador.fora@test.com",
            nome="Operador Fora",
            grupo=cls.grupo_operador,
            unidade_administrativa=cls.ua_fora,
            unidade_orcamentaria=cls.uo2,
        )
        cls.superuser = cls._criar_usuario(
            username=f"{prefix}superuser",
            email=f"{prefix}superuser@test.com",
            nome="Superuser",
            grupo=cls.grupo_gestor,
            is_superuser=True,
            unidade_orcamentaria=cls.uo1,
        )

    def setUp(self):
        super().setUp()
        self.conciliacao_ua1 = self._criar_conciliacao(
            self.ua1, periodo=date(2025, 8, 23)
        )
        self.conciliacao_ua2 = self._criar_conciliacao(
            self.ua2, periodo=date(2025, 9, 1)
        )
        self.conciliacao_fora = self._criar_conciliacao(
            self.ua_fora,
            criado_por=self.operador_fora,
            periodo=date(2025, 9, 1),
        )

    def _criar_conciliacao(self, ua, criado_por=None, periodo=None):
        return ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=periodo,
            unidade_administrativa=ua,
            criado_por=criado_por or self.gestor_com_ua,
        )

    def _criar_bem(self, ua, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Descrição",
            "valor_unitario": Decimal("100.00"),
            "marca": "Marca",
            "modelo": "Modelo",
            "status": bem_constants.APROVADO,
            "unidade_administrativa": ua,
            "criado_por": self.gestor_com_ua,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _auth(self, user):
        self.client.force_authenticate(user)
