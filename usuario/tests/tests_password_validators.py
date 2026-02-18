from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from usuario.models import Usuario
from usuario.validators import PasswordComplexityValidator


class PasswordValidatorsTestCase(TestCase):

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
        senha_sem_letras = "123@456"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_sem_letras, self.usuario)

        errors = str(context.exception)
        self.assertIn("pelo menos uma letra", errors.lower())

    def test_senha_sem_numeros(self):
        senha_sem_numeros = "Senha@abc"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_sem_numeros, self.usuario)

        errors = str(context.exception)
        self.assertIn("pelo menos um número", errors.lower())

    def test_senha_sem_caracteres_especiais(self):
        senha_sem_especiais = "Senha123"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_sem_especiais, self.usuario)

        errors = str(context.exception)
        self.assertIn("pelo menos um caractere especial", errors.lower())

    def test_senha_com_informacoes_pessoais_username(self):
        senha_com_username = "joao.silva@123"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_com_username, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_similar" in str(error.code) for error in errors)
        )

    def test_senha_com_informacoes_pessoais_nome(self):
        senha_com_nome = "Silva@123"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_com_nome, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_similar" in str(error.code) for error in errors)
        )

    def test_senha_com_informacoes_pessoais_email(self):
        senha_com_email = "joao.silva@prefeitura1!"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_com_email, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_similar" in str(error.code) for error in errors)
        )

    def test_multiplos_erros_validacao(self):
        senha_invalida = "abc"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_invalida, self.usuario)

        self.assertGreater(len(context.exception.error_list), 1)

    def test_senha_muito_comum(self):
        senha_comum = "password"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_comum, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_too_common" in str(error.code) for error in errors)
        )

    def test_senha_totalmente_numerica(self):
        senha_numerica = "123456"

        with self.assertRaises(ValidationError) as context:
            validate_password(senha_numerica, self.usuario)

        errors = context.exception.error_list
        self.assertTrue(
            any("password_entirely_numeric" in str(error.code) for error in errors)
        )

    def test_caracteres_especiais_diversos(self):
        caracteres_especiais = ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"]

        for char in caracteres_especiais:
            senha = f"Senha1{char}"
            with self.subTest(char=char):
                try:
                    validate_password(senha, self.usuario)
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
