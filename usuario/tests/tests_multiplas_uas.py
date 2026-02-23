from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from rest_framework import status
from rest_framework.test import APITestCase

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.constants import APROVADO
from dados_comuns.libs.unidade_administrativa import uas_do_usuario
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.admin import CustomUserModelAdmin
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class OperadorMultiplasUAsAPITestCase(APITestCase):

    def setUp(self):
        self.uo = criar_uo(codigo="UO-001", nome="UO Teste")
        self.ua1 = criar_ua(uo=self.uo, codigo="UA-001", sigla="UA1", nome="UA 1")
        self.ua2 = criar_ua(uo=self.uo, codigo="UA-002", sigla="UA2", nome="UA 2")
        self.ua3 = criar_ua(uo=self.uo, codigo="UA-003", sigla="UA3", nome="UA 3")

        self.uo2 = criar_uo(codigo="UO-002", nome="UO Outra")
        self.ua_outra = criar_ua(
            uo=self.uo2, codigo="UA-099", sigla="UAX", nome="UA Outra UO"
        )

        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.operador = Usuario.objects.create_user(
            username="operador_multi",
            email="operador@test.com",
            password="test123",
            nome="Operador Multi",
            is_staff=True,
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua1,
        )
        self.operador.groups.add(self.grupo_operador)
        self.operador.unidades_administrativas.add(self.ua1, self.ua2, self.ua3)

        self.selecionar_ua_url = "/api/auth/me/selecionar-ua/"
        self.me_url = "/api/auth/me/"

    def test_operador_troca_escopo_para_ua2(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua2.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.operador.refresh_from_db()
        self.assertEqual(self.operador.unidade_administrativa_id, self.ua2.id)

    def test_operador_troca_escopo_para_ua3(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua3.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.operador.refresh_from_db()
        self.assertEqual(self.operador.unidade_administrativa_id, self.ua3.id)

    def test_operador_nao_pode_selecionar_ua_fora_do_m2m(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua_outra.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_operador_nao_pode_selecionar_ua_null(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.post(
            self.selecionar_ua_url,
            {
                "unidade_administrativa_id": None,
                "unidade_orcamentaria_id": self.uo.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_opcoes_escopo_retorna_todas_uas_do_m2m(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.get(self.me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        grupos = resp.data["opcoes_escopo"]["grupos"]
        self.assertEqual(len(grupos), 1)
        grupo = grupos[0]
        ua_ids = {ua["id"] for ua in grupo["uas"]}
        self.assertIn(self.ua1.id, ua_ids)
        self.assertIn(self.ua2.id, ua_ids)
        self.assertIn(self.ua3.id, ua_ids)
        self.assertEqual(len(ua_ids), 3)


class AdminValidacaoM2MTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = CustomUserModelAdmin(Usuario, self.site)
        self.factory = RequestFactory()

        self.uo = criar_uo(codigo="UO-001", nome="UO Teste")
        self.ua1 = criar_ua(uo=self.uo, codigo="UA-001", sigla="UA1", nome="UA 1")
        self.ua2 = criar_ua(uo=self.uo, codigo="UA-002", sigla="UA2", nome="UA 2")

        self.uo2 = criar_uo(codigo="UO-002", nome="UO Outra")
        self.ua_outra = criar_ua(
            uo=self.uo2, codigo="UA-099", sigla="UAX", nome="UA Outra UO"
        )

        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]
        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]

        self.superuser = Usuario.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="test123",
            is_staff=True,
        )

    def _get_form(self, obj=None, post_data=None):
        if post_data:
            request = self.factory.post("/admin/usuario/usuario/add/", data=post_data)
        else:
            request = self.factory.get("/admin/usuario/usuario/add/")
        request.user = self.superuser
        request._obj_usuario_admin = obj
        return self.admin.get_form(request, obj=obj)

    def test_operador_sem_uas_no_m2m_erro(self):
        data = {
            "username": "op_sem_m2m",
            "password1": "Teste@12345!x",
            "password2": "Teste@12345!x",
            "nome": "Operador Sem M2M",
            "email": "op@test.com",
            "is_staff": True,
            "groups": [self.grupo_operador.id],
            "unidade_orcamentaria": self.uo.id,
            "unidade_administrativa": self.ua1.id,
            "unidades_administrativas": [],
        }
        form_class = self._get_form(post_data=data)
        form = form_class(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("unidades_administrativas", form.errors)

    def test_ua_ativa_fora_do_m2m_erro(self):
        data = {
            "username": "op_fora_m2m",
            "password1": "Teste@12345!x",
            "password2": "Teste@12345!x",
            "nome": "Operador Fora M2M",
            "email": "op2@test.com",
            "is_staff": True,
            "groups": [self.grupo_operador.id],
            "unidade_orcamentaria": self.uo.id,
            "unidade_administrativa": self.ua1.id,
            "unidades_administrativas": [self.ua2.id],
        }
        form_class = self._get_form(post_data=data)
        form = form_class(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("unidade_administrativa", form.errors)

    def test_uas_de_uo_diferente_erro(self):
        data = {
            "username": "op_uo_diff",
            "password1": "Teste@12345!x",
            "password2": "Teste@12345!x",
            "nome": "Operador UO Diff",
            "email": "op3@test.com",
            "is_staff": True,
            "groups": [self.grupo_operador.id],
            "unidade_orcamentaria": self.uo.id,
            "unidade_administrativa": self.ua1.id,
            "unidades_administrativas": [self.ua1.id, self.ua_outra.id],
        }
        form_class = self._get_form(post_data=data)
        form = form_class(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("unidades_administrativas", form.errors)


class UasDOUsuarioTestCase(TestCase):

    def setUp(self):
        self.uo = criar_uo(codigo="UO-001", nome="UO Teste")
        self.ua1 = criar_ua(uo=self.uo, codigo="UA-001", sigla="UA1", nome="UA 1")
        self.ua2 = criar_ua(uo=self.uo, codigo="UA-002", sigla="UA2", nome="UA 2")
        self.ua3 = criar_ua(uo=self.uo, codigo="UA-003", sigla="UA3", nome="UA 3")

        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.operador = Usuario.objects.create_user(
            username="operador_uas",
            password="test123",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua1,
        )
        self.operador.groups.add(self.grupo_operador)
        self.operador.unidades_administrativas.add(self.ua1, self.ua2, self.ua3)

    def test_retorna_todas_uas_do_m2m(self):
        qs = uas_do_usuario(self.operador)
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.ua1.id, self.ua2.id, self.ua3.id})

    def test_fallback_para_fk_se_m2m_vazio(self):
        user = Usuario.objects.create_user(
            username="op_sem_m2m",
            password="test123",
            unidade_administrativa=self.ua1,
        )
        qs = uas_do_usuario(user)
        self.assertEqual(list(qs.values_list("id", flat=True)), [self.ua1.id])


class EmailMovimentacaoM2MTestCase(TestCase):

    def setUp(self):
        self.uo = criar_uo(codigo="UO-001", nome="UO Teste")
        self.ua_origem = criar_ua(
            uo=self.uo, codigo="UA-001", sigla="UA1", nome="UA Origem"
        )
        self.ua_destino = criar_ua(
            uo=self.uo, codigo="UA-002", sigla="UA2", nome="UA Destino"
        )

        grupo_operador = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)[0]

        self.operador_origem = Usuario.objects.create_user(
            username="op_origem",
            email="origem@test.com",
            password="test123",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.operador_origem.groups.add(grupo_operador)
        self.operador_origem.unidades_administrativas.add(self.ua_origem)

        self.operador_multi = Usuario.objects.create_user(
            username="op_multi",
            email="multi@test.com",
            password="test123",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.operador_multi.groups.add(grupo_operador)
        self.operador_multi.unidades_administrativas.add(
            self.ua_origem, self.ua_destino
        )

        self.bem = BemPatrimonial.objects.create(
            nome="Cadeira",
            numero_patrimonial="001.000000001-0",
            marca="Marca",
            modelo="Modelo",
            descricao="Desc",
            valor_unitario=100,
            numero_processo="123",
            criado_por=self.operador_origem,
            status=APROVADO,
            unidade_administrativa=self.ua_origem,
        )

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_notifica_operador_com_ua_no_m2m_mas_nao_ativo_nela(self, mock_send):
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=self.bem)

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        emails = call_args[3]
        self.assertIn("multi@test.com", emails)


class UasPermitidasPropertyTestCase(TestCase):

    def setUp(self):
        self.uo = criar_uo(codigo="UO-001", nome="UO Teste")
        self.ua1 = criar_ua(uo=self.uo, codigo="UA-001", sigla="UA1", nome="UA 1")
        self.ua2 = criar_ua(uo=self.uo, codigo="UA-002", sigla="UA2", nome="UA 2")

        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]
        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]

    def test_operador_retorna_m2m(self):
        operador = Usuario.objects.create_user(
            username="op",
            password="t",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua1,
        )
        operador.groups.add(self.grupo_operador)
        operador.unidades_administrativas.add(self.ua1, self.ua2)

        ids = set(operador.uas_permitidas.values_list("id", flat=True))
        self.assertEqual(ids, {self.ua1.id, self.ua2.id})

    def test_gestor_retorna_todas_uas_da_uo(self):
        gestor = Usuario.objects.create_user(
            username="ge",
            password="t",
            unidade_orcamentaria=self.uo,
        )
        gestor.groups.add(self.grupo_gestor)

        ids = set(gestor.uas_permitidas.values_list("id", flat=True))
        self.assertIn(self.ua1.id, ids)
        self.assertIn(self.ua2.id, ids)

    def test_superuser_retorna_todas_ativas(self):
        su = Usuario.objects.create_superuser(
            username="su",
            password="t",
            email="su@t.com",
        )
        total_ativas = UnidadeAdministrativa.objects.filter(
            status=UnidadeAdministrativa.ATIVA
        ).count()
        self.assertEqual(su.uas_permitidas.count(), total_ativas)
