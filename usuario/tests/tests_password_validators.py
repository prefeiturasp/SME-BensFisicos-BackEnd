from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from usuario.models import Usuario
from usuario.validators import PasswordComplexityValidator


class PasswordValidatorsTestCase(TestCase):

    @staticmethod
    def _montar_valor_teste(*partes):
        return "".join(partes)

    def setUp(self):
        self.usuario = Usuario(
            username="joao.silva",
            nome="João da Silva",
            email="joao.silva@prefeitura.sp.gov.br",
            rf="1234567",
        )

    def test_senha_valida_completa(self):
        senhas_validas = [
            "Senha@123",
            "MyP@ssw0rd",
            "Admin#2024",
            "Secure!Pass9",
            "Test$123abc",
        ]

        for senha in senhas_validas:
            with self.subTest(senha=senha):
                try:
                    validate_password(senha, self.usuario)
                except ValidationError:
                    self.fail(f"Senha válida '{senha}' foi rejeitada incorretamente")

    def test_senha_minimo_6_caracteres(self):
        senhas_curtas = ["Ab@1", "A@1", "Test@"]

        for senha in senhas_curtas:
            with self.subTest(senha=senha):
                with self.assertRaises(ValidationError) as context:
                    validate_password(senha, self.usuario)

                errors = str(context.exception)
                self.assertIn("6 caracteres", errors.lower())

    def test_senha_sem_letras(self):
        valor_teste = self._montar_valor_teste("123", "@", "456")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = str(context.exception)
        self.assertIn("pelo menos uma letra", errors.lower())

    def test_senha_sem_numeros(self):
        valor_teste = self._montar_valor_teste("Senha", "@", "abc")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = str(context.exception)
        self.assertIn("pelo menos um número", errors.lower())

    def test_senha_sem_caracteres_especiais(self):
        valor_teste = self._montar_valor_teste("Senha", "123")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = str(context.exception)
        self.assertIn("pelo menos um caractere especial", errors.lower())

    def test_senha_com_informacoes_pessoais_username(self):
        valor_teste = self._montar_valor_teste("joao", ".", "silva", "@", "123")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_similar" in str(error.code) for error in errors)
        )

    def test_senha_com_informacoes_pessoais_nome(self):
        valor_teste = self._montar_valor_teste("Silva", "@", "123")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_similar" in str(error.code) for error in errors)
        )

    def test_senha_com_informacoes_pessoais_email(self):
        valor_teste = self._montar_valor_teste(
            "joao", ".", "silva", "@", "prefeitura", "1", "!"
        )

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_similar" in str(error.code) for error in errors)
        )

    def test_multiplos_erros_validacao(self):
        valor_teste = self._montar_valor_teste("a", "b", "c")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        self.assertGreater(len(context.exception.error_list), 1)

    def test_senha_muito_comum(self):
        valor_teste = self._montar_valor_teste("pass", "word")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_common" in str(error.code) for error in errors)
        )

    def test_senha_totalmente_numerica(self):
        valor_teste = self._montar_valor_teste("123", "456")

        with self.assertRaises(ValidationError) as context:
            validate_password(valor_teste, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_entirely_numeric" in str(error.code) for error in errors)
        )

    def test_caracteres_especiais_diversos(self):
        caracteres_especiais = ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"]

        for char in caracteres_especiais:
            valor_teste = self._montar_valor_teste("Senha", "1", char)
            with self.subTest(char=char):
                try:
                    validate_password(valor_teste, self.usuario)
                except ValidationError:
                    self.fail(
                        f"Senha com caractere especial '{char}' deveria ser válida"
                    )


class PasswordComplexityValidatorTestCase(TestCase):

    def setUp(self):
        self.validator = PasswordComplexityValidator()

    def test_get_help_text(self):
        help_text = self.validator.get_help_text()
        self.assertIn("letras, números e caracteres especiais", help_text.lower())
