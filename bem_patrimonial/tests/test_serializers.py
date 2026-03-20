from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.serializers.bem_patrimonial_serializers import (
    BemPatrimonialDetailSerializer,
    BemPatrimonialListSerializer,
    BemPatrimonialMultiCreateSerializer,
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


class BemPatrimonialMultiCreateSerializerTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin_multi",
            email="admin_multi@example.com",
            **auth_kwargs("admin123"),
        )
        self.uo = criar_uo(codigo="200", nome="UO 200")
        self.ua = criar_ua(nome="UA Multi", uo=self.uo)

        self.user.unidade_administrativa = self.ua
        self.user.save()

        self.factory = RequestFactory()

    def _get_request(self):
        request = self.factory.post("/fake/")
        request.user = self.user
        return request

    def _payload_base(self, **kwargs):
        data = {
            "unidade_administrativa": self.ua.id,
            "nome": "Mesa",
            "descricao": "Mesa de escritório",
            "valor_unitario": "1.500,00",
            "marca": "Tokio",
            "modelo": "T200",
            "numero_processo": "PROC-99",
        }
        data.update(kwargs)
        return data

    def _item(self, **kwargs):
        item = {
            "numero_patrimonial": "000.000000001-0",
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            "localizacao": "Sala A",
        }
        item.update(kwargs)
        return item

    # ------------------------------------------------------------------
    # Casos de sucesso
    # ------------------------------------------------------------------

    def test_cria_um_bem_com_numero_valido(self):
        data = self._payload_base(multi_payload=[self._item()])
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_cria_multiplos_bens_com_numeros_distintos(self):
        data = self._payload_base(
            multi_payload=[
                self._item(numero_patrimonial="000.000000011-0"),
                self._item(numero_patrimonial="000.000000012-0"),
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_cria_bem_sem_numeracao(self):
        data = self._payload_base(
            multi_payload=[
                {
                    "numero_patrimonial": "",
                    "numero_formato_antigo": False,
                    "sem_numeracao": True,
                    "localizacao": "Sala B",
                }
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_cria_bem_com_formato_antigo(self):
        data = self._payload_base(
            multi_payload=[
                self._item(
                    numero_patrimonial="ANTIGO-123",
                    numero_formato_antigo=True,
                )
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_valor_unitario_aceita_formato_brasileiro(self):
        data = self._payload_base(
            valor_unitario="2.500,99",
            multi_payload=[self._item(numero_patrimonial="000.000000020-0")],
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertTrue(s.is_valid(), s.errors)
        from decimal import Decimal
        self.assertEqual(s.validated_data["valor_unitario"], Decimal("2500.99"))

    # ------------------------------------------------------------------
    # Validação de campos base obrigatórios
    # ------------------------------------------------------------------

    def test_erro_sem_nome(self):
        data = self._payload_base(
            nome="", multi_payload=[self._item(numero_patrimonial="000.000000030-0")]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("nome", s.errors)

    def test_erro_sem_descricao(self):
        data = self._payload_base(
            descricao="",
            multi_payload=[self._item(numero_patrimonial="000.000000031-0")],
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("descricao", s.errors)

    def test_erro_sem_marca(self):
        data = self._payload_base(
            marca="", multi_payload=[self._item(numero_patrimonial="000.000000032-0")]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("marca", s.errors)

    def test_erro_sem_modelo(self):
        data = self._payload_base(
            modelo="", multi_payload=[self._item(numero_patrimonial="000.000000033-0")]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("modelo", s.errors)

    def test_erro_multi_payload_vazio(self):
        data = self._payload_base(multi_payload=[])
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("multi_payload", s.errors)

    # ------------------------------------------------------------------
    # Validação por linha
    # ------------------------------------------------------------------

    def test_erro_numero_formato_invalido_retorna_erros_por_linha(self):
        data = self._payload_base(
            multi_payload=[
                self._item(
                    numero_patrimonial="INVALIDO",
                    numero_formato_antigo=False,
                )
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("linhas", s.errors)
        self.assertIn("0", s.errors["linhas"])
        self.assertIn("numero_patrimonial", s.errors["linhas"]["0"])

    def test_erro_sem_numero_e_sem_flag_sem_numeracao(self):
        data = self._payload_base(
            multi_payload=[
                self._item(
                    numero_patrimonial="",
                    sem_numeracao=False,
                )
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("linhas", s.errors)

    def test_erro_sem_numeracao_e_formato_antigo_juntos(self):
        data = self._payload_base(
            multi_payload=[
                self._item(
                    numero_patrimonial="",
                    sem_numeracao=True,
                    numero_formato_antigo=True,
                )
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("linhas", s.errors)

    def test_erro_duplicata_no_payload(self):
        numero = "000.000000050-0"
        data = self._payload_base(
            multi_payload=[
                self._item(numero_patrimonial=numero),
                self._item(numero_patrimonial=numero),
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("linhas", s.errors)
        # segundo item (índice 1) deve ter o erro de duplicata
        self.assertIn("1", s.errors["linhas"])
        self.assertIn(
            "duplicado", s.errors["linhas"]["1"]["numero_patrimonial"].lower()
        )

    def test_erro_numero_ja_cadastrado_no_banco(self):
        numero = "000.000000060-0"
        BemPatrimonial.objects.create(
            nome="Existente",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_patrimonial=numero,
            numero_formato_antigo=False,
            sem_numeracao=False,
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.AGUARDANDO_APROVACAO,
        )

        data = self._payload_base(
            multi_payload=[self._item(numero_patrimonial=numero)]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        self.assertIn("linhas", s.errors)
        self.assertIn("cadastrado", s.errors["linhas"]["0"]["numero_patrimonial"].lower())

    def test_erro_em_linha_nao_impede_validacao_das_demais(self):
        """Todos os erros por linha são coletados antes de retornar."""
        data = self._payload_base(
            multi_payload=[
                self._item(numero_patrimonial="INVALIDO_1", numero_formato_antigo=False),
                self._item(numero_patrimonial="000.000000070-0"),
                self._item(numero_patrimonial="INVALIDO_2", numero_formato_antigo=False),
            ]
        )
        s = BemPatrimonialMultiCreateSerializer(
            data=data, context={"request": self._get_request()}
        )
        self.assertFalse(s.is_valid())
        linhas = s.errors["linhas"]
        self.assertIn("0", linhas)
        self.assertNotIn("1", linhas)  # linha válida não tem erro
        self.assertIn("2", linhas)
