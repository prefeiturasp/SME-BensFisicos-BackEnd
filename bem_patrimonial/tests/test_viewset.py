from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants
from dados_comuns.tests.factories import criar_ua, criar_uo


class BemPatrimonialViewSetTest(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin123",
        )

        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.uo = criar_uo(codigo="110", nome="UO 110")
        self.ua = criar_ua(nome="UA Teste", uo=self.uo)

        self.user.unidade_administrativa = self.ua
        self.user.save()

    def _mk_bem(self, **kwargs):
        count = BemPatrimonial.objects.count() + 1
        data = {
            "nome": f"Item {count}",
            "numero_patrimonial": f"000.00000000{count:02d}-0",
            "descricao": "Desc",
            "valor_unitario": 1.00,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            "criado_por": self.user,
            "unidade_administrativa": self.ua,
            "status": constants.AGUARDANDO_APROVACAO,
        }
        data.update(kwargs)
        return BemPatrimonial.objects.create(**data)

    def test_list_bens(self):
        self._mk_bem()
        self._mk_bem()

        url = reverse("bens-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_list_bens_com_param_baixados_mais_de_um_periodo(self):
        url = reverse("bens-list")
        response = self.client.get(url, {"baixados_mais_de_um_periodo": "1"})
        self.assertEqual(response.status_code, 200)

    def test_aprovar_bens_sucesso(self):
        bem1 = self._mk_bem()
        bem2 = self._mk_bem()

        url = reverse("bens-aprovar-bens")
        response = self.client.post(url, {"ids": [bem1.id, bem2.id]}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["aprovados"], 2)

        bem1.refresh_from_db()
        self.assertEqual(bem1.status, constants.APROVADO)

    def test_aprovar_bens_sem_ids_retorna_400(self):
        url = reverse("bens-aprovar-bens")
        response = self.client.post(url, {"ids": []}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ids", response.data)

    def test_aprovar_bens_quando_nenhum_aguardando(self):
        bem = self._mk_bem(status=constants.APROVADO)

        url = reverse("bens-aprovar-bens")
        response = self.client.post(url, {"ids": [bem.id]}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["aprovados"], 0)
        self.assertEqual(response.data["ignorados"], 1)

    def test_aprovar_bens_misturado(self):
        bem_ok = self._mk_bem(status=constants.AGUARDANDO_APROVACAO)
        bem_ign = self._mk_bem(status=constants.APROVADO)

        url = reverse("bens-aprovar-bens")
        response = self.client.post(
            url, {"ids": [bem_ok.id, bem_ign.id]}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["aprovados"], 1)
        self.assertEqual(response.data["ignorados"], 1)

    def test_reprovar_bens_sucesso(self):
        bem1 = self._mk_bem()
        bem2 = self._mk_bem()

        url = reverse("bens-reprovar-bens")
        response = self.client.post(url, {"ids": [bem1.id, bem2.id]}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reprovados"], 2)

        bem1.refresh_from_db()
        self.assertEqual(bem1.status, constants.NAO_APROVADO)

    def test_reprovar_bens_sem_ids_retorna_400(self):
        url = reverse("bens-reprovar-bens")
        response = self.client.post(url, {"ids": None}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_reprovar_bens_quando_nenhum_aguardando(self):
        bem = self._mk_bem(status=constants.APROVADO)

        url = reverse("bens-reprovar-bens")
        response = self.client.post(url, {"ids": [bem.id]}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reprovados"], 0)
        self.assertEqual(response.data["ignorados"], 1)
