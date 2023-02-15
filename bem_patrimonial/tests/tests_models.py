import datetime
from django.test import TestCase
from bem_patrimonial.models import BemPatrimonial


class SetupData:
    def create_instance(self):

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
            "numero_serie": None
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
