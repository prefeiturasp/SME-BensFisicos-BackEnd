from django.test import TestCase
from django.contrib.auth.models import Group

from usuario.models import Usuario
from dados_comuns.models import UnidadeAdministrativa
from usuario.constants import GRUPO_OPERADOR_INVENTARIO


class SetupData:
    def create_unidade(self):
        UnidadeAdministrativa.objects.create(codigo=123, nome="COTIC", sigla="COTIC")

    def create_instance(self):
        self.create_unidade()

        obj = {
            "username": "usuario",
            "password": "@@User20201",
            "nome": "Veronica Silva",
            "email": "usuario@gmail.com",
            "unidade_administrativa": UnidadeAdministrativa.objects.first(),
            "is_staff": True
        }
        usuario = Usuario.objects.create(**obj)
        self.add_group(usuario)

        return usuario

    def add_group(self, usuario):
        group_operador_inventario, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        usuario.groups.add(group_operador_inventario)


class UsuarioTestCase(TestCase):
    start = SetupData()
    entity = Usuario

    def setUp(self):
        self.start.create_instance()

    def test_get(self):
        instance = self.entity.objects.first()
        self.assertIsInstance(instance, self.entity)

    def test_delete(self):
        instance = self.entity.objects.first()
        instance.delete()

        self.assertFalse(instance.id)
        self.assertIsInstance(instance, self.entity)
