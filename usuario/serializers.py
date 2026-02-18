from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from usuario.models import Usuario


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)

        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "nome": self.user.nome,
            "rf": self.user.rf,
            "is_gestor_patrimonio": self.user.is_gestor_patrimonio,
            "is_operador_inventario": self.user.is_operador_inventario,
            "must_change_password": self.user.must_change_password,
            "unidade_administrativa": (
                {
                    "id": self.user.unidade_administrativa.id,
                    "nome": self.user.unidade_administrativa.nome,
                }
                if self.user.unidade_administrativa
                else None
            ),
        }

        return data


class PasswordResetRequestSerializer(serializers.Serializer):

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        from django.contrib.auth.tokens import PasswordResetTokenGenerator
        from django.utils.http import urlsafe_base64_decode

        try:
            uid = urlsafe_base64_decode(attrs["uidb64"]).decode()
            user = Usuario.objects.get(pk=uid, is_active=True)
        except (Usuario.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError({"token": "Token inválido ou expirado."})

        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Token inválido ou expirado."})

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "As senhas não conferem."}
            )

        attrs["user"] = user
        return attrs

    def save(self):
        from django.utils import timezone

        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.last_password_change = timezone.now()
        user.save()
        return user


class PasswordChangeSerializer(serializers.Serializer):

    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Senha atual incorreta.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "As senhas não conferem."}
            )
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.save()
        return user


class FirstAccessPasswordChangeSerializer(serializers.Serializer):

    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        user = self.context["request"].user

        if not getattr(user, "must_change_password", False):
            raise serializers.ValidationError(
                {"detail": "Usuário não está marcado para troca obrigatória de senha."}
            )

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "As senhas não conferem."}
            )

        return attrs

    def save(self):
        from django.utils import timezone

        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.last_password_change = timezone.now()
        user.save(
            update_fields=["password", "must_change_password", "last_password_change"]
        )
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    is_gestor_patrimonio = serializers.BooleanField(read_only=True)
    is_operador_inventario = serializers.BooleanField(read_only=True)
    unidade_administrativa = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "nome",
            "rf",
            "is_gestor_patrimonio",
            "is_operador_inventario",
            "must_change_password",
            "unidade_administrativa",
        ]
        read_only_fields = fields

    def get_unidade_administrativa(self, obj):
        ua = obj.unidade_administrativa
        if ua:
            return {"id": ua.id, "nome": ua.nome}
        return None
