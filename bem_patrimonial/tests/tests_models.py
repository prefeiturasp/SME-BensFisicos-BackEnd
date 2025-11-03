import re
import datetime
from django.test import TestCase
from django.db import IntegrityError
from django.core.exceptions import ValidationError

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.constants import (
    APROVADO,
    NAO_APROVADO,
    AGUARDANDO_APROVACAO,
)
from usuario.tests import tests_models as usuariotests_models

# O model atual formata como: 000.{12 dígitos}-0
NPAT_REGEX = r"^\d{3}\.\d{12}-\d$"


class SetupData:
    def create_instance(self):
        setup_usuario = usuariotests_models.SetupData()
        criado_por = setup_usuario.create_instance()

        obj = {
            "nome": "Mesa reta",
            "descricao": "Mesa reta fortline ferro",
            "valor_unitario": 255.57,
            "marca": "Fortline",
            "modelo": "Reta",
            "numero_processo": "349573",
            "numero_patrimonial": None,
            "localizacao": "Escritório",
            "criado_por": criado_por,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
        }
        return BemPatrimonial.objects.create(**obj)


class BemPatrimonialTestCase(TestCase):
    start = SetupData()
    entity = BemPatrimonial

    def setUp(self):
        self.instance = self.start.create_instance()

    def test_get(self):
        instance = self.entity.objects.first()
        self.assertIsInstance(instance, self.entity)
        self.assertEqual(instance.status, AGUARDANDO_APROVACAO)

    def test_update(self):
        instance = self.entity.objects.first()
        instance.nome = "Mesa triunfo 2"
        instance.save()
        self.assertEqual(instance.nome, "Mesa triunfo 2")

    def test_delete(self):
        instance = self.entity.objects.first()
        pk = instance.pk
        instance.delete()
        self.assertFalse(self.entity.objects.filter(pk=pk).exists())
        self.assertIsInstance(instance, self.entity)

    def test_nao_aprovado_status_change_sync(self):
        instance = self.entity.objects.first()
        instance.statusbempatrimonial_set.create(status=NAO_APROVADO)
        self.assertEqual(
            instance.status, instance.statusbempatrimonial_set.last().status
        )
        self.assertEqual(instance.status, NAO_APROVADO)

    def test_aprovado_status_change_sync(self):
        instance = self.entity.objects.first()
        instance.statusbempatrimonial_set.create(status=APROVADO)
        self.assertEqual(
            instance.status, instance.statusbempatrimonial_set.last().status
        )
        self.assertEqual(instance.status, APROVADO)

    def test_regex_valido_quando_formato_novo_e_sem_flags(self):
        obj = self.entity(
            nome="CPU",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="1",
            numero_patrimonial="000.000000123-4",
            numero_formato_antigo=False,
            sem_numeracao=False,
            criado_por=self.instance.criado_por,
        )
        obj.full_clean()

    def test_regex_invalido_quando_formato_novo(self):
        obj = self.entity(
            nome="CPU",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="2",
            numero_patrimonial="000.0000123-44",  # formato inválido p/ 12 dígitos
            numero_formato_antigo=False,
            sem_numeracao=False,
            criado_por=self.instance.criado_por,
        )
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("numero_patrimonial", ctx.exception.message_dict)

    def test_formato_antigo_nao_valida_regex(self):
        obj = self.entity(
            nome="Monitor",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="3",
            numero_patrimonial="valor_livre",  # permitido c/ formato antigo
            numero_formato_antigo=True,
            sem_numeracao=False,
            criado_por=self.instance.criado_por,
        )
        obj.full_clean()  # não deve levantar erro

    def test_flags_sao_exclusivas(self):
        obj = self.entity(
            nome="Mouse",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="4",
            numero_patrimonial=None,
            numero_formato_antigo=True,
            sem_numeracao=True,
            criado_por=self.instance.criado_por,
        )
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()

        self.assertTrue(any("Sem numeração" in m for m in ctx.exception.messages))

    def test_bloqueia_salvar_sem_numero_quando_nao_sem_numeracao(self):
        obj = self.entity(
            nome="Teclado",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="5",
            numero_patrimonial=None,
            numero_formato_antigo=False,
            sem_numeracao=False,
            criado_por=self.instance.criado_por,
        )
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("numero_patrimonial", ctx.exception.message_dict)

    def test_sem_numeracao_gera_numero_automatico_formatado(self):
        obj = self.entity(
            nome="Cadeira",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="6",
            numero_patrimonial=None,
            numero_formato_antigo=False,
            sem_numeracao=True,
            criado_por=self.instance.criado_por,
        )
        obj.full_clean()
        obj.save()
        self.assertIsNotNone(obj.numero_patrimonial)
        # "000." + 12 dígitos + "-0" -> total esperado = 4 + 12 + 2 = 18
        self.assertEqual(len(obj.numero_patrimonial), 18)
        self.assertRegex(obj.numero_patrimonial, NPAT_REGEX)

    def test_unicidade_numero_patrimonial(self):
        a = self.entity.objects.create(
            nome="Item1",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="7",
            numero_patrimonial="000.000000000111-2",
            numero_formato_antigo=False,
            sem_numeracao=False,
            criado_por=self.instance.criado_por,
        )
        self.assertIsNotNone(a.pk)

        with self.assertRaises(IntegrityError):
            self.entity.objects.create(
                nome="Item2",
                descricao="Desc",
                valor_unitario=1,
                marca="M",
                modelo="X",
                numero_processo="8",
                numero_patrimonial="000.000000000111-2",  # duplicado
                numero_formato_antigo=True,
                sem_numeracao=False,
                criado_por=self.instance.criado_por,
            )

    def test_sem_numeracao_incrementa_em_caso_de_colisao(self):
        """
        1) Cria um bem A (sem_numeracao=True) para firmar PK.
        2) Reserva manualmente o número que seria usado pelo próximo (B-holder).
        3) Cria um bem C (sem_numeracao=True) e verifica que ele incrementou e não colidiu.
        """
        a = self.entity.objects.create(
            nome="A",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="10",
            numero_patrimonial=None,
            numero_formato_antigo=False,
            sem_numeracao=True,
            criado_por=self.instance.criado_por,
        )
        self.assertIsNotNone(a.numero_patrimonial)

        next_id = a.pk + 1
        id12 = str(next_id).zfill(12)
        esperado_proximo = f"000.{id12}-0"

        b_holder = self.entity.objects.create(
            nome="B-holder",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="11",
            numero_patrimonial=esperado_proximo,  # ocupando o próximo número
            numero_formato_antigo=True,  # formato antigo permite salvar livre
            sem_numeracao=False,
            criado_por=self.instance.criado_por,
        )
        self.assertEqual(b_holder.numero_patrimonial, esperado_proximo)

        c = self.entity.objects.create(
            nome="C",
            descricao="Desc",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="12",
            numero_patrimonial=None,
            numero_formato_antigo=False,
            sem_numeracao=True,
            criado_por=self.instance.criado_por,
        )
        self.assertRegex(c.numero_patrimonial, NPAT_REGEX)
        self.assertNotEqual(c.numero_patrimonial, esperado_proximo)
