from django.test import TestCase
from dados_comuns.models import UnidadeAdministrativa


class SetupData:
    def create_instance(self):

        obj = {
            "codigo": 39684596,
            "sigla":  "COTIC",
            "nome": "Centro de tecnologia",
        }      
        UnidadeAdministrativa.objects.create(**obj)


class UnidadeAdministrativaTestCase(TestCase):
    start = SetupData()
    entity = UnidadeAdministrativa

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
