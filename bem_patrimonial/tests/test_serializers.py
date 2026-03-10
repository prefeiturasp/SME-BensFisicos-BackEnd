from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.serializers.bem_patrimonial_serializers import (
    BemPatrimonialDetailSerializer,
    BemPatrimonialListSerializer,
)
from bem_patrimonial import constants
from dados_comuns.tests.factories import criar_ua, criar_uo


class BemPatrimonialSerializerTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            **auth_kwargs("admin123"),
        )

        self.uo = criar_uo(codigo="100", nome="UO 100")
        self.ua = criar_ua(nome="UA Teste", unidade_orcamentaria=self.uo)

        self.user.unidade_administrativa = self.ua
        self.user.save()

        self.factory = RequestFactory()

    def _get_request(self):
        request = self.factory.post("/fake-url/")
        request.user = self.user
        return request

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

    def test_list_serializer_inclui_status_display_e_ua_nome_codigo(self):
        bem = self._mk_bem(status=constants.APROVADO)
        s = BemPatrimonialListSerializer(instance=bem)
        data = s.data
        self.assertIn("status_display", data)
        self.assertIn("unidade_administrativa_nome", data)
        self.assertIn("unidade_administrativa_codigo", data)

    def test_nao_permite_editar_baixa_fisica(self):
        bem = self._mk_bem(status=constants.BAIXA_FISICA)

        serializer = BemPatrimonialDetailSerializer(
            instance=bem,
            data={"nome": "Novo Nome"},
            context={"request": self._get_request()},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("Baixa Física", str(serializer.errors))

    def test_nao_permite_alterar_unidade(self):
        outra_uo = criar_uo(codigo="999", nome="UO 999")
        outra_ua = criar_ua(nome="Outra UA", uo=outra_uo)

        bem = self._mk_bem()

        serializer = BemPatrimonialDetailSerializer(
            instance=bem,
            data={"unidade_administrativa": outra_ua.id},
            context={"request": self._get_request()},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("unidade_administrativa", serializer.errors)

    def test_create_forca_status_aguardando_e_criado_por(self):
        request = self._get_request()

        serializer = BemPatrimonialDetailSerializer(
            data={
                "nome": "Novo",
                "descricao": "Desc",
                "valor_unitario": 10,
                "marca": "M",
                "modelo": "X",
                "numero_patrimonial": "000.000000999-0",
                "numero_formato_antigo": False,
                "sem_numeracao": False,
                "unidade_administrativa": self.ua.id,
            },
            context={"request": request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        obj = serializer.save()

        self.assertEqual(obj.status, constants.AGUARDANDO_APROVACAO)
        self.assertEqual(obj.criado_por, self.user)

    def test_valor_unitario_obrigatorio_no_create(self):
        request = self._get_request()
        serializer = BemPatrimonialDetailSerializer(
            data={
                "nome": "Novo",
                "descricao": "Desc",
                "marca": "M",
                "modelo": "X",
                "numero_patrimonial": "000.000000998-0",
                "numero_formato_antigo": False,
                "sem_numeracao": False,
                "unidade_administrativa": self.ua.id,
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("valor_unitario", serializer.errors)

    def test_numero_patrimonial_formato_invalido_quando_nao_antigo(self):
        bem = self._mk_bem()
        serializer = BemPatrimonialDetailSerializer(
            instance=bem,
            data={"numero_patrimonial": "123", "numero_formato_antigo": False},
            context={"request": self._get_request()},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("numero_patrimonial", serializer.errors)

    def test_update_duplicidade_numero_patrimonial(self):
        bem1 = self._mk_bem(numero_patrimonial="000.000000111-0")
        bem2 = self._mk_bem(numero_patrimonial="000.000000222-0")

        serializer = BemPatrimonialDetailSerializer(
            instance=bem2,
            data={
                "numero_patrimonial": bem1.numero_patrimonial,
                "numero_formato_antigo": False,
            },
            context={"request": self._get_request()},
            partial=True,
        )
        if serializer.is_valid():
            with self.assertRaises(Exception):
                serializer.save()
        else:
            self.assertIn("numero_patrimonial", serializer.errors)
