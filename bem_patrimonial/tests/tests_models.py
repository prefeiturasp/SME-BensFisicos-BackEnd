import datetime
from django.test import TestCase
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.constants import APROVADO, NAO_APROVADO, AGUARDANDO_APROVACAO
from usuario.tests import tests_models as usuariotests_models


class SetupData:
    def create_instance(self):
        setup_usuario = usuariotests_models.SetupData()
        criado_por = setup_usuario.create_instance()

        obj = {
            "nome": "Mesa reta",
            "data_compra_entrega":  datetime.date.today(),
            "origem": 1,
            "marca": "Fortline",
            "modelo": "Reta",
            "quantidade": 100,
            "descricao": "Mesa reta fortline ferro",
            "valor_unitario": 255.57,
            "numero_processo": 349573,
            "autorizacao_no_doc_em": datetime.date.today(),
            "numero_nibpm": 432434,
            "numero_cimbpm": 4354534,
            "numero_patrimonial": None,
            "localizacao": "Escritório",
            "numero_serie": None,
            "criado_por": criado_por
        }
        BemPatrimonial.objects.create(**obj)


class BemPatrimonialTestCase(TestCase):
    start = SetupData()
    entity = BemPatrimonial

    def setUp(self):
        self.start.create_instance()

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
        instance.delete()

        self.assertFalse(instance.id)
        self.assertIsInstance(instance, self.entity)

    def test_nao_aprovado_status_change_sync(self):
        instance = self.entity.objects.first()
        instance.statusbempatrimonial_set.create(
            status=NAO_APROVADO
        )
        self.assertEqual(instance.status, instance.statusbempatrimonial_set.last().status)
        self.assertEqual(instance.status, NAO_APROVADO)

    def test_aprovado_status_change_sync(self):
        instance = self.entity.objects.first()
        instance.statusbempatrimonial_set.create(
            status=APROVADO
        )
        self.assertEqual(instance.status, instance.statusbempatrimonial_set.last().status)
        self.assertEqual(instance.status, APROVADO)
