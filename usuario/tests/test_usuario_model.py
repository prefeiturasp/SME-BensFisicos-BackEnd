"""Testes para usuario.models.Usuario (clean, is_gestor_patrimonio, is_operador_inventario)."""
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class UsuarioCleanTestCase(TestCase):
    """Testes para Usuario.clean (validação UO/UA)."""

    def setUp(self):
        self.uo = criar_uo(codigo="701")
        self.ua = criar_ua(uo=self.uo, codigo="701", nome="UA Teste")

    def test_ua_sem_uo_levanta_erro(self):
        """Usuario com UA e sem UO levanta ValidationError."""
        u = Usuario(
            username="test",
            email="t@t.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=None,
        )
        u.set_password("x")
        with self.assertRaises(ValidationError) as ctx:
            u.clean()
        self.assertIn("unidade_orcamentaria", ctx.exception.message_dict)

    def test_ua_de_outra_uo_levanta_erro(self):
        """Usuario com UA que não pertence à UO informada levanta ValidationError."""
        outro_uo = criar_uo(codigo="702")
        u = Usuario(
            username="test",
            email="t@t.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=outro_uo,
        )
        u.set_password("x")
        with self.assertRaises(ValidationError) as ctx:
            u.clean()
        self.assertIn("unidade_administrativa", ctx.exception.message_dict)

    def test_ua_e_uo_coerentes_nao_levanta(self):
        """Usuario com UA da mesma UO não levanta erro."""
        u = Usuario(
            username="test",
            email="t@t.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        u.set_password("x")
        u.clean()


class UsuarioPropertiesTestCase(TestCase):
    """Testes para is_gestor_patrimonio e is_operador_inventario."""

    def setUp(self):
        self.uo = criar_uo(codigo="801")
        self.ua = criar_ua(uo=self.uo, codigo="801", nome="UA")
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )

    def test_sem_grupos_ambos_false(self):
        """Usuario sem grupos tem is_gestor e is_operador False."""
        u = Usuario.objects.create_user(
            username="nobody",
            password="x",
            email="n@n.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.assertFalse(u.is_gestor_patrimonio)
        self.assertFalse(u.is_operador_inventario)

    def test_gestor_patrimonio_true_com_grupo(self):
        """Usuario no grupo GESTOR_PATRIMONIO tem is_gestor_patrimonio True."""
        u = Usuario.objects.create_user(
            username="gestor",
            password="x",
            email="g@g.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        u.groups.add(self.grupo_gestor)
        self.assertTrue(u.is_gestor_patrimonio)
        self.assertFalse(u.is_operador_inventario)

    def test_operador_inventario_true_com_grupo(self):
        """Usuario no grupo OPERADOR_INVENTARIO tem is_operador_inventario True."""
        u = Usuario.objects.create_user(
            username="operador",
            password="x",
            email="o@o.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        u.groups.add(self.grupo_operador)
        self.assertFalse(u.is_gestor_patrimonio)
        self.assertTrue(u.is_operador_inventario)

    def test_ambos_grupos_ambas_true(self):
        """Usuario em ambos os grupos tem as duas properties True."""
        u = Usuario.objects.create_user(
            username="ambos",
            password="x",
            email="a@a.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        u.groups.add(self.grupo_gestor)
        u.groups.add(self.grupo_operador)
        self.assertTrue(u.is_gestor_patrimonio)
        self.assertTrue(u.is_operador_inventario)
