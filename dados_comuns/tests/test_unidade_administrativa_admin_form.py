"""Testes para dados_comuns.forms.unidade_administrativa_admin_form."""
from django.core.exceptions import ValidationError
from django.test import TestCase

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from dados_comuns.forms.unidade_administrativa_admin_form import (
    UnidadeAdministrativaAdminForm,
)


class TestUnidadeAdministrativaAdminForm(TestCase):
    """Testes para UnidadeAdministrativaAdminForm."""

    def setUp(self):
        self.uo = criar_uo(codigo="100")

    def test_init_com_instancia_sem_codigo(self):
        """Init com instância sem código não define initial."""
        ua = criar_ua(uo=self.uo)
        # Remove o código para simular instância sem código
        ua.codigo = ""
        ua.save()
        form = UnidadeAdministrativaAdminForm(instance=ua)
        # Se não há código, o initial pode ser None ou vazio
        initial = form.fields["codigo_sufixo"].initial
        self.assertTrue(initial is None or initial == "")

    def test_init_com_instancia_codigo_com_ponto(self):
        """Init com instância com código contendo ponto extrai sufixo."""
        ua = criar_ua(uo=self.uo, codigo="100.286")
        form = UnidadeAdministrativaAdminForm(instance=ua)
        self.assertEqual(form.fields["codigo_sufixo"].initial, "286")

    def test_init_com_instancia_codigo_sem_ponto(self):
        """Init com instância com código sem ponto usa código completo."""
        ua = criar_ua(uo=self.uo, codigo="286")
        form = UnidadeAdministrativaAdminForm(instance=ua)
        self.assertEqual(form.fields["codigo_sufixo"].initial, "286")

    def test_clean_codigo_sufixo_valido_1_digito(self):
        """Aceita sufixo com 1 dígito e preenche com zeros à esquerda."""
        form = UnidadeAdministrativaAdminForm()
        form.cleaned_data = {"codigo_sufixo": "5"}
        resultado = form.clean_codigo_sufixo()
        self.assertEqual(resultado, "005")

    def test_clean_codigo_sufixo_valido_2_digitos(self):
        """Aceita sufixo com 2 dígitos e preenche com zero à esquerda."""
        form = UnidadeAdministrativaAdminForm()
        form.cleaned_data = {"codigo_sufixo": "28"}
        resultado = form.clean_codigo_sufixo()
        self.assertEqual(resultado, "028")

    def test_clean_codigo_sufixo_valido_3_digitos(self):
        """Aceita sufixo com 3 dígitos."""
        form = UnidadeAdministrativaAdminForm()
        form.cleaned_data = {"codigo_sufixo": "286"}
        resultado = form.clean_codigo_sufixo()
        self.assertEqual(resultado, "286")

    def test_clean_codigo_sufixo_invalido_com_letras(self):
        """Rejeita sufixo com letras."""
        form = UnidadeAdministrativaAdminForm()
        form.cleaned_data = {"codigo_sufixo": "28A"}
        with self.assertRaises(ValidationError):
            form.clean_codigo_sufixo()

    def test_clean_codigo_sufixo_invalido_mais_3_digitos(self):
        """Rejeita sufixo com mais de 3 dígitos."""
        form = UnidadeAdministrativaAdminForm()
        form.cleaned_data = {"codigo_sufixo": "1234"}
        with self.assertRaises(ValidationError):
            form.clean_codigo_sufixo()

    def test_clean_codigo_sufixo_vazio(self):
        """Rejeita sufixo vazio."""
        form = UnidadeAdministrativaAdminForm()
        form.cleaned_data = {"codigo_sufixo": ""}
        with self.assertRaises(ValidationError):
            form.clean_codigo_sufixo()

    def test_clean_sem_unidade_orcamentaria_erro(self):
        """Clean sem unidade_orcamentaria gera erro."""
        form = UnidadeAdministrativaAdminForm(
            data={
                "codigo_sufixo": "286",
                "sigla": "UA",
                "nome": "Unidade",
                "status": UnidadeAdministrativa.ATIVA,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("unidade_orcamentaria", form.errors)

    def test_clean_sem_codigo_sufixo_erro(self):
        """Clean sem codigo_sufixo gera erro."""
        form = UnidadeAdministrativaAdminForm(
            data={
                "unidade_orcamentaria": self.uo.pk,
                "sigla": "UA",
                "nome": "Unidade",
                "status": UnidadeAdministrativa.ATIVA,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("codigo_sufixo", form.errors)

    def test_clean_monta_codigo_completo(self):
        """Clean monta código completo a partir de UO e sufixo."""
        form = UnidadeAdministrativaAdminForm(
            data={
                "unidade_orcamentaria": self.uo.pk,
                "codigo_sufixo": "286",
                "sigla": "UA",
                "nome": "Unidade",
                "status": UnidadeAdministrativa.ATIVA,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo"], "100.286")

    def test_clean_remove_espacos_do_sufixo(self):
        """Clean remove espaços do sufixo antes de montar código."""
        form = UnidadeAdministrativaAdminForm(
            data={
                "unidade_orcamentaria": self.uo.pk,
                "codigo_sufixo": " 286 ",
                "sigla": "UA",
                "nome": "Unidade",
                "status": UnidadeAdministrativa.ATIVA,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["codigo"], "100.286")
