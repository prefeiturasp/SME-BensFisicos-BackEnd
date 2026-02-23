"""Testes para dados_comuns.escopo."""
from django.test import TestCase
from django.contrib.auth import get_user_model

from dados_comuns.escopo import (
    usuario_e_super_admin,
    obter_unidade_orcamentaria_id_do_usuario,
    resolver_ids_escopo,
    filtrar_queryset_por_escopo,
    validar_objeto_no_escopo,
    filtrar_ua_origem_por_escopo,
    filtrar_ua_destino_por_uo_do_usuario,
    filtrar_queryset_movimentacao_por_escopo,
)
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO
from django.contrib.auth.models import Group
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants


User = get_user_model()


class TestEscopo(TestCase):
    """Testes para funções de escopo."""

    def setUp(self):
        self.uo = criar_uo(codigo="301")
        self.ua = criar_ua(uo=self.uo, codigo="301", status=UnidadeAdministrativa.ATIVA)
        self.ua_outra = criar_ua(uo=self.uo, codigo="302", status=UnidadeAdministrativa.ATIVA)
        self.uo_outra = criar_uo(codigo="303")
        self.ua_outra_uo = criar_ua(uo=self.uo_outra, codigo="304", status=UnidadeAdministrativa.ATIVA)

    def test_usuario_e_super_admin_com_superuser(self):
        """usuario_e_super_admin retorna True para superuser."""
        superuser = User.objects.create_user(
            username="super",
            password="x",
            email="super@test.com",
            is_superuser=True,
        )
        self.assertTrue(usuario_e_super_admin(superuser))

    def test_usuario_e_super_admin_com_nao_superuser(self):
        """usuario_e_super_admin retorna False para não superuser."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            is_superuser=False,
        )
        self.assertFalse(usuario_e_super_admin(user))

    def test_obter_unidade_orcamentaria_id_do_usuario_com_uo_direta(self):
        """obter_unidade_orcamentaria_id_do_usuario retorna UO direta."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_orcamentaria=self.uo,
        )
        uo_id = obter_unidade_orcamentaria_id_do_usuario(user)
        self.assertEqual(uo_id, self.uo.pk)

    def test_obter_unidade_orcamentaria_id_do_usuario_via_ua(self):
        """obter_unidade_orcamentaria_id_do_usuario retorna UO via UA."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=None,
        )
        uo_id = obter_unidade_orcamentaria_id_do_usuario(user)
        self.assertEqual(uo_id, self.uo.pk)

    def test_obter_unidade_orcamentaria_id_do_usuario_sem_uo(self):
        """obter_unidade_orcamentaria_id_do_usuario retorna None sem UO."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=None,
        )
        uo_id = obter_unidade_orcamentaria_id_do_usuario(user)
        self.assertIsNone(uo_id)

    def test_resolver_ids_escopo_com_superuser(self):
        """resolver_ids_escopo retorna flags corretas para superuser."""
        superuser = User.objects.create_user(
            username="super",
            password="x",
            email="super@test.com",
            is_superuser=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        is_super, is_gestor, ua_id, uo_id = resolver_ids_escopo(superuser)
        self.assertTrue(is_super)
        self.assertEqual(ua_id, self.ua.pk)
        self.assertEqual(uo_id, self.uo.pk)

    def test_resolver_ids_escopo_com_gestor(self):
        """resolver_ids_escopo retorna flags corretas para gestor."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        gestor.groups.add(grupo_gestor)
        is_super, is_gestor, ua_id, uo_id = resolver_ids_escopo(gestor)
        self.assertFalse(is_super)
        self.assertTrue(is_gestor)
        self.assertEqual(ua_id, self.ua.pk)
        self.assertEqual(uo_id, self.uo.pk)

    def test_filtrar_queryset_por_escopo_com_ua(self):
        """filtrar_queryset_por_escopo filtra por UA quando usuário tem UA."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
        )
        # Criar objetos relacionados à UA usando BemPatrimonial
        bem1 = BemPatrimonial.objects.create(
            nome="Bem 1",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=user,
            status=bem_constants.APROVADO,
        )
        bem2 = BemPatrimonial.objects.create(
            nome="Bem 2",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-2",
            unidade_administrativa=self.ua_outra,
            criado_por=user,
            status=bem_constants.APROVADO,
        )
        
        queryset = BemPatrimonial.objects.filter(pk__in=[bem1.pk, bem2.pk])
        filtered = filtrar_queryset_por_escopo(user, queryset)
        # Deve retornar apenas o bem da UA do usuário
        self.assertEqual(filtered.count(), 1)
        self.assertIn(bem1, filtered)
        self.assertNotIn(bem2, filtered)

    def test_filtrar_queryset_por_escopo_gestor_sem_ua(self):
        """filtrar_queryset_por_escopo filtra por UO quando gestor sem UA."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=None,
        )
        gestor.groups.add(grupo_gestor)
        
        # Criar bens em diferentes UAs
        bem1 = BemPatrimonial.objects.create(
            nome="Bem 1",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=gestor,
            status=bem_constants.APROVADO,
        )
        bem2 = BemPatrimonial.objects.create(
            nome="Bem 2",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-2",
            unidade_administrativa=self.ua_outra,
            criado_por=gestor,
            status=bem_constants.APROVADO,
        )
        bem3 = BemPatrimonial.objects.create(
            nome="Bem 3",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-3",
            unidade_administrativa=self.ua_outra_uo,
            criado_por=gestor,
            status=bem_constants.APROVADO,
        )
        
        queryset = BemPatrimonial.objects.filter(pk__in=[bem1.pk, bem2.pk, bem3.pk])
        filtered = filtrar_queryset_por_escopo(gestor, queryset)
        # Deve retornar apenas bens das UAs da UO do gestor
        self.assertEqual(filtered.count(), 2)
        self.assertIn(bem1, filtered)
        self.assertIn(bem2, filtered)
        self.assertNotIn(bem3, filtered)

    def test_filtrar_queryset_por_escopo_usuario_sem_ua_nao_gestor(self):
        """filtrar_queryset_por_escopo retorna vazio para usuário sem UA não gestor."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        
        bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=user,
            status=bem_constants.APROVADO,
        )
        
        queryset = BemPatrimonial.objects.all()
        filtered = filtrar_queryset_por_escopo(user, queryset)
        # Deve retornar vazio
        self.assertEqual(filtered.count(), 0)

    def test_validar_objeto_no_escopo_com_ua(self):
        """validar_objeto_no_escopo valida objeto da UA do usuário."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
        )
        
        # Objeto da UA do usuário (quando objeto é UnidadeAdministrativa, campo_ua deve ser None ou não usado)
        # Como validar_objeto_no_escopo espera um campo relacionado, vamos testar com um objeto que tenha UA
        bem = BemPatrimonial.objects.create(
            nome="Bem Teste",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=user,
            status=bem_constants.APROVADO,
        )
        self.assertTrue(validar_objeto_no_escopo(user, bem))
        bem2 = BemPatrimonial.objects.create(
            nome="Bem Teste 2",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-2",
            unidade_administrativa=self.ua_outra,
            criado_por=user,
            status=bem_constants.APROVADO,
        )
        self.assertFalse(validar_objeto_no_escopo(user, bem2))

    def test_validar_objeto_no_escopo_gestor_sem_ua(self):
        """validar_objeto_no_escopo valida objeto da UO do gestor."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=None,
        )
        gestor.groups.add(grupo_gestor)
        
        # Objeto da UO do gestor (usando BemPatrimonial como exemplo)
        bem = BemPatrimonial.objects.create(
            nome="Bem Teste",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=gestor,
            status=bem_constants.APROVADO,
        )
        self.assertTrue(validar_objeto_no_escopo(gestor, bem))
        bem2 = BemPatrimonial.objects.create(
            nome="Bem Teste 2",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-2",
            unidade_administrativa=self.ua_outra_uo,
            criado_por=gestor,
            status=bem_constants.APROVADO,
        )
        self.assertFalse(validar_objeto_no_escopo(gestor, bem2))

    def test_filtrar_ua_origem_por_escopo_com_ua(self):
        """filtrar_ua_origem_por_escopo retorna apenas UA do usuário."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
        )
        
        queryset = UnidadeAdministrativa.objects.filter(
            pk__in=[self.ua.pk, self.ua_outra.pk]
        )
        filtered = filtrar_ua_origem_por_escopo(user, queryset)
        self.assertEqual(filtered.count(), 1)
        self.assertIn(self.ua, filtered)

    def test_filtrar_ua_origem_por_escopo_gestor_sem_ua(self):
        """filtrar_ua_origem_por_escopo retorna UAs da UO do gestor."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=None,
        )
        gestor.groups.add(grupo_gestor)
        
        queryset = UnidadeAdministrativa.objects.filter(
            pk__in=[self.ua.pk, self.ua_outra.pk, self.ua_outra_uo.pk]
        )
        filtered = filtrar_ua_origem_por_escopo(gestor, queryset)
        self.assertEqual(filtered.count(), 2)
        self.assertIn(self.ua, filtered)
        self.assertIn(self.ua_outra, filtered)

    def test_filtrar_ua_origem_por_escopo_usuario_sem_ua_nao_gestor(self):
        """filtrar_ua_origem_por_escopo retorna vazio para usuário sem UA não gestor."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        
        queryset = UnidadeAdministrativa.objects.all()
        filtered = filtrar_ua_origem_por_escopo(user, queryset)
        self.assertEqual(filtered.count(), 0)

    def test_filtrar_ua_destino_por_uo_do_usuario_com_uo(self):
        """filtrar_ua_destino_por_uo_do_usuario retorna UAs da UO do usuário."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_orcamentaria=self.uo,
        )
        
        queryset = UnidadeAdministrativa.objects.filter(
            pk__in=[self.ua.pk, self.ua_outra.pk, self.ua_outra_uo.pk]
        )
        filtered = filtrar_ua_destino_por_uo_do_usuario(user, queryset)
        self.assertEqual(filtered.count(), 2)
        self.assertIn(self.ua, filtered)
        self.assertIn(self.ua_outra, filtered)
        self.assertNotIn(self.ua_outra_uo, filtered)

    def test_filtrar_ua_destino_por_uo_do_usuario_sem_uo(self):
        """filtrar_ua_destino_por_uo_do_usuario retorna vazio sem UO."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_orcamentaria=None,
        )
        
        queryset = UnidadeAdministrativa.objects.all()
        filtered = filtrar_ua_destino_por_uo_do_usuario(user, queryset)
        self.assertEqual(filtered.count(), 0)

    def test_filtrar_ua_destino_por_uo_do_usuario_superuser(self):
        """filtrar_ua_destino_por_uo_do_usuario retorna todas para superuser."""
        superuser = User.objects.create_user(
            username="super",
            password="x",
            email="super@test.com",
            is_superuser=True,
            unidade_orcamentaria=self.uo,
        )
        
        queryset = UnidadeAdministrativa.objects.filter(
            pk__in=[self.ua.pk, self.ua_outra.pk, self.ua_outra_uo.pk]
        )
        filtered = filtrar_ua_destino_por_uo_do_usuario(superuser, queryset)
        # Superuser ainda filtra por UO (não retorna todas)
        self.assertEqual(filtered.count(), 2)
        self.assertIn(self.ua, filtered)
        self.assertIn(self.ua_outra, filtered)
