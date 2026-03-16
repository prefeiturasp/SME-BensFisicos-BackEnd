from dados_comuns.tests.auth_test_utils import auth_kwargs
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
            **auth_kwargs("admin123"),
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


class CreateMultiViewSetTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin_multi_vs",
            email="admin_multi_vs@example.com",
            **auth_kwargs("admin123"),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.uo = criar_uo(codigo="300", nome="UO 300")
        self.ua = criar_ua(nome="UA Multi VS", uo=self.uo)

        self.user.unidade_administrativa = self.ua
        self.user.save()

    def _url(self):
        return reverse("bens-create-multi")

    def _payload(self, multi_payload=None):
        return {
            "unidade_administrativa": self.ua.id,
            "nome": "Cadeira",
            "descricao": "Cadeira ergonômica",
            "valor_unitario": "500,00",
            "marca": "Flexform",
            "modelo": "Ergo500",
            "numero_processo": "PROC-01",
            "multi_payload": multi_payload if multi_payload is not None else [
                {
                    "numero_patrimonial": "000.000000100-0",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "Sala 1",
                }
            ],
        }

    def test_create_multi_retorna_201(self):
        response = self.client.post(self._url(), self._payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["count"], 1)

    def test_create_multi_cria_bens_no_banco(self):
        self.client.post(self._url(), self._payload(), format="json")
        self.assertEqual(
            BemPatrimonial.objects.filter(numero_patrimonial="000.000000100-0").count(),
            1,
        )

    def test_create_multi_status_aguardando_aprovacao(self):
        self.client.post(self._url(), self._payload(), format="json")
        bem = BemPatrimonial.objects.get(numero_patrimonial="000.000000100-0")
        self.assertEqual(bem.status, constants.AGUARDANDO_APROVACAO)

    def test_create_multi_criado_por_e_ua_corretos(self):
        self.client.post(self._url(), self._payload(), format="json")
        bem = BemPatrimonial.objects.get(numero_patrimonial="000.000000100-0")
        self.assertEqual(bem.criado_por, self.user)
        self.assertEqual(bem.unidade_administrativa, self.ua)

    def test_create_multi_multiplos_bens(self):
        payload = self._payload(
            multi_payload=[
                {
                    "numero_patrimonial": "000.000000101-0",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "Sala 1",
                },
                {
                    "numero_patrimonial": "000.000000102-0",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "Sala 2",
                },
            ]
        )
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            BemPatrimonial.objects.filter(
                numero_patrimonial__in=["000.000000101-0", "000.000000102-0"]
            ).count(),
            2,
        )

    def test_create_multi_sem_numeracao(self):
        payload = self._payload(
            multi_payload=[
                {
                    "numero_patrimonial": "",
                    "numero_formato_antigo": False,
                    "sem_numeracao": True,
                    "localizacao": "",
                }
            ]
        )
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 201)

    def test_create_multi_numero_invalido_retorna_400_com_erros_por_linha(self):
        payload = self._payload(
            multi_payload=[
                {
                    "numero_patrimonial": "INVALIDO",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "",
                }
            ]
        )
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("linhas", response.data)
        self.assertIn("0", response.data["linhas"])

    def test_create_multi_duplicata_no_banco_retorna_400(self):
        BemPatrimonial.objects.create(
            nome="Existente",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_patrimonial="000.000000110-0",
            numero_formato_antigo=False,
            sem_numeracao=False,
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.AGUARDANDO_APROVACAO,
        )
        payload = self._payload(
            multi_payload=[
                {
                    "numero_patrimonial": "000.000000110-0",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "",
                }
            ]
        )
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("linhas", response.data)

    def test_create_multi_duplicata_no_payload_retorna_400(self):
        numero = "000.000000120-0"
        payload = self._payload(
            multi_payload=[
                {
                    "numero_patrimonial": numero,
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "",
                },
                {
                    "numero_patrimonial": numero,
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "",
                },
            ]
        )
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("linhas", response.data)

    def test_create_multi_rollback_se_algum_invalido(self):
        """Nenhum bem é persistido se qualquer linha for inválida."""
        count_antes = BemPatrimonial.objects.count()
        payload = self._payload(
            multi_payload=[
                {
                    "numero_patrimonial": "000.000000130-0",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "",
                },
                {
                    "numero_patrimonial": "INVALIDO",
                    "numero_formato_antigo": False,
                    "sem_numeracao": False,
                    "localizacao": "",
                },
            ]
        )
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)

    def test_create_multi_payload_vazio_retorna_400(self):
        payload = self._payload(multi_payload=[])
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_create_multi_campo_base_obrigatorio_faltando_retorna_400(self):
        payload = self._payload()
        del payload["nome"]
        response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("nome", response.data)
