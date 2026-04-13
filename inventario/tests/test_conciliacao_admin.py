from datetime import date

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse

from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BemPatrimonial
from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_ua, criar_uo
from inventario import constants
from inventario.admin import ConciliacaoUAAdmin, ItemConciliacaoAdmin
from inventario.forms import ConciliacaoUAAdminForm
from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from usuario.constants import GRUPO_GESTOR_PATRIMONIO


class ConciliacaoAdminBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uo = criar_uo(codigo="230", nome="UO Teste Admin", sigla="UO-ADM")
        cls.ua = criar_ua(
            uo=cls.uo,
            codigo="001.0234",
            sigla="ITA",
            nome="Unidade Administrativa Teste",
        )
        cls.outra_ua = criar_ua(
            uo=cls.uo,
            codigo="001.9999",
            sigla="OUT",
            nome="Outra Unidade Administrativa",
        )

        cls.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        user_model = get_user_model()
        cls.superuser = user_model.objects.create_superuser(
            username="super_conciliacao_admin",
            email="super.conciliacao@example.com",
            **auth_kwargs("senha123"),
        )
        cls.superuser.unidade_orcamentaria = cls.uo
        cls.superuser.must_change_password = False
        cls.superuser.save(
            update_fields=["unidade_orcamentaria", "must_change_password"]
        )
        cls.superuser.groups.add(cls.grupo_gestor)

        cls.criador = user_model.objects.create_user(
            username="gestor_conciliacao_admin",
            **auth_kwargs("senha123"),
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        cls.criador.must_change_password = False
        cls.criador.save(update_fields=["must_change_password"])
        cls.criador.groups.add(cls.grupo_gestor)

        cls.conciliacao = ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 8, 23),
            unidade_administrativa=cls.ua,
            criado_por=cls.criador,
        )
        cls.outra_conciliacao = ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 9, 1),
            unidade_administrativa=cls.outra_ua,
            criado_por=cls.criador,
        )

        cls.bem_1 = BemPatrimonial.objects.create(
            numero_patrimonial="SEM-NUMERO-251",
            nome="Bem Estresse Realista 1",
            descricao="Descricao 1",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=cls.ua,
            criado_por=cls.criador,
        )
        cls.bem_2 = BemPatrimonial.objects.create(
            numero_patrimonial="SEM-NUMERO-252",
            nome="Bem Estresse Realista 2",
            descricao="Descricao 2",
            valor_unitario=200,
            status=bem_constants.APROVADO,
            unidade_administrativa=cls.ua,
            criado_por=cls.criador,
        )
        cls.bem_outro = BemPatrimonial.objects.create(
            numero_patrimonial="SEM-NUMERO-999",
            nome="Bem Fora da Conciliacao",
            descricao="Descricao 999",
            valor_unitario=300,
            status=bem_constants.APROVADO,
            unidade_administrativa=cls.outra_ua,
            criado_por=cls.criador,
        )

        cls.item_sem_ocorrencia = ItemConciliacao.objects.create(
            conciliacao=cls.conciliacao,
            bem=cls.bem_1,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        cls.item_com_ocorrencia = ItemConciliacao.objects.create(
            conciliacao=cls.conciliacao,
            bem=cls.bem_2,
            situacao=constants.DIVERGENTE,
            observacao="Divergencia identificada",
            divergencia="Etiqueta danificada",
        )
        OcorrenciaConciliacao.objects.create(
            item=cls.item_com_ocorrencia,
            situacao=constants.DIVERGENTE,
            observacao="Divergencia identificada",
            divergencia="Etiqueta danificada",
            registrado_por=cls.criador,
        )

        cls.item_outra_conciliacao = ItemConciliacao.objects.create(
            conciliacao=cls.outra_conciliacao,
            bem=cls.bem_outro,
            situacao=constants.NAO_ENCONTRADO,
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.conciliacao_admin = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        self.item_admin = ItemConciliacaoAdmin(ItemConciliacao, self.site)


class ConciliacaoUAAdminFormTest(ConciliacaoAdminBaseTest):
    def test_form_em_edicao_mantem_campos_bloqueados(self):
        request = self.factory.get("/admin/")
        request.user = self.superuser
        form = ConciliacaoUAAdminForm(instance=self.conciliacao, request=request)

        self.assertTrue(form.fields["unidade_administrativa"].disabled)
        self.assertTrue(form.fields["tipo"].disabled)
        self.assertTrue(form.fields["periodo_final"].disabled)


class ConciliacaoAdminMethodsTest(ConciliacaoAdminBaseTest):
    def test_get_itens_conciliacao_url_monta_query_da_conciliacao(self):
        url = self.conciliacao_admin._get_itens_conciliacao_url(self.conciliacao)

        self.assertIn(reverse("admin:inventario_itemconciliacao_changelist"), url)
        self.assertIn(f"conciliacao__id__exact={self.conciliacao.pk}", url)

    def test_situacao_display_renderiza_badge_padronizado(self):
        html = self.item_admin.situacao_display(self.item_com_ocorrencia)

        self.assertIn("min-width: 148px", html)
        self.assertIn("justify-content:center", html.replace(" ", ""))
        self.assertIn("Divergente", html)

    def test_acoes_lista_renderiza_botoes_com_gap(self):
        html = self.item_admin.acoes_lista(self.item_com_ocorrencia)

        self.assertIn("display:flex", html)
        self.assertIn("flex-direction:column", html)
        self.assertIn("gap:4px", html)
        self.assertIn("Editar", html)
        self.assertIn("Excluir", html)


class ItemConciliacaoChangeListViewTest(ConciliacaoAdminBaseTest):
    def test_changelist_da_conciliacao_exibe_so_contexto_da_conciliacao(self):
        url = reverse("admin:inventario_itemconciliacao_changelist")
        response = self.client.get(url, {"conciliacao__id__exact": self.conciliacao.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"Itens da Conciliação {self.conciliacao.numero_conciliacao}",
        )
        self.assertContains(response, "Voltar para a Conciliação")
        self.assertContains(response, "Gerenciamento de Conciliações")
        self.assertContains(response, self.bem_1.numero_patrimonial)
        self.assertContains(response, self.bem_2.numero_patrimonial)
        self.assertNotContains(response, self.bem_outro.numero_patrimonial)
        self.assertNotContains(response, "Conciliação</th>")
        self.assertNotContains(response, "total)")

    def test_changelist_filtra_por_nome_do_bem(self):
        url = reverse("admin:inventario_itemconciliacao_changelist")
        response = self.client.get(
            url,
            {
                "conciliacao__id__exact": self.conciliacao.pk,
                "q": "Realista 2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.bem_2.numero_patrimonial)
        self.assertNotContains(response, self.bem_1.numero_patrimonial)

    def test_change_view_exibe_voltar_com_filtro_preservado(self):
        url = reverse(
            "admin:inventario_itemconciliacao_change",
            args=[self.item_sem_ocorrencia.pk],
        )
        response = self.client.get(
            url,
            {"_changelist_filters": f"conciliacao__id__exact={self.conciliacao.pk}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'href="/admin/inventario/itemconciliacao/?conciliacao__id__exact={self.conciliacao.pk}"',
        )
        self.assertContains(response, ">Voltar<", html=False)
        self.assertNotContains(response, ">Close<", html=False)

    def test_change_view_sem_filtro_preservado_volta_para_conciliacao_correta(self):
        url = reverse(
            "admin:inventario_itemconciliacao_change",
            args=[self.item_sem_ocorrencia.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'href="/admin/inventario/itemconciliacao/?conciliacao__id__exact={self.conciliacao.pk}"',
        )

    def test_history_view_exibe_voltar_para_change_do_item(self):
        url = reverse(
            "admin:inventario_itemconciliacao_history",
            args=[self.item_sem_ocorrencia.pk],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'href="/admin/inventario/itemconciliacao/{self.item_sem_ocorrencia.pk}/change/"',
        )
        self.assertContains(response, ">Voltar<", html=False)


class RegistrarOcorrenciaAdminViewTest(ConciliacaoAdminBaseTest):
    def test_get_registrar_ocorrencia_renderiza_fluxo_admin_com_botoes_novos(self):
        url = reverse(
            "admin:inventario_item_registrar_ocorrencia",
            args=[self.item_com_ocorrencia.pk],
        )
        response = self.client.get(
            url,
            {"next": self.conciliacao_admin._get_itens_conciliacao_url(self.conciliacao)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gerenciamento de Conciliações")
        self.assertContains(response, "Itens de Conciliação")
        self.assertContains(response, "Salvar e voltar")
        self.assertContains(response, "Voltar")
        self.assertNotContains(response, "Cancelar")

    def test_post_sem_situacao_exibe_validacao_em_portugues(self):
        url = reverse(
            "admin:inventario_item_registrar_ocorrencia",
            args=[self.item_sem_ocorrencia.pk],
        )
        response = self.client.post(
            url,
            {"situacao": "", "observacao": "Obs", "divergencia": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecione uma situação.")
        self.assertNotContains(response, "Please select an item in the list.")
