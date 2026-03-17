from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth.password_validation import validate_password
from usuario.models import Usuario
from django.utils import timezone
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria, HistoricoGeral
from dados_comuns.escopo import obter_unidade_orcamentaria_id_do_usuario
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
import re
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

MSG_SENHAS_NAO_CONFEREM = "As senhas não conferem."

User = get_user_model()


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
                {"new_password_confirm": MSG_SENHAS_NAO_CONFEREM}
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
                {"new_password_confirm": MSG_SENHAS_NAO_CONFEREM}
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
                {"new_password_confirm": MSG_SENHAS_NAO_CONFEREM}
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
    uo_ativa = serializers.SerializerMethodField()
    ua_ativa = serializers.SerializerMethodField()
    opcoes_escopo = serializers.SerializerMethodField()

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
            "uo_ativa",
            "ua_ativa",
            "opcoes_escopo",
        ]
        read_only_fields = fields

    def get_uo_ativa(self, obj):
        uo = obj.unidade_orcamentaria
        if not uo and obj.unidade_administrativa:
            uo = obj.unidade_administrativa.unidade_orcamentaria
        if uo:
            return {
                "id": uo.id,
                "codigo": uo.codigo,
                "nome": uo.nome,
                "label": f"{uo.codigo} - {uo.nome}",
            }
        return None

    def get_ua_ativa(self, obj):
        ua = obj.unidade_administrativa
        if ua:
            return {
                "id": ua.id,
                "codigo": ua.codigo,
                "nome": ua.nome,
                "label": f"{ua.codigo} - {ua.nome}",
            }
        return None

    def get_opcoes_escopo(self, obj):
        uos_qs = UnidadeOrcamentaria.objects.none()
        uas_qs = UnidadeAdministrativa.objects.none()

        if obj.is_superuser:
            uos_qs = UnidadeOrcamentaria.objects.filter(ativa=True)
            uas_qs = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
        elif obj.is_gestor_patrimonio:
            uo_id = obter_unidade_orcamentaria_id_do_usuario(obj)
            if uo_id:
                uos_qs = UnidadeOrcamentaria.objects.filter(id=uo_id, ativa=True)
                uas_qs = UnidadeAdministrativa.objects.filter(
                    unidade_orcamentaria_id=uo_id,
                    status=UnidadeAdministrativa.ATIVA,
                )
        elif obj.is_operador_inventario:
            uas_qs = obj.unidades_administrativas.filter(
                status=UnidadeAdministrativa.ATIVA
            )
            uo_id = obter_unidade_orcamentaria_id_do_usuario(obj)
            if uo_id:
                uos_qs = UnidadeOrcamentaria.objects.filter(id=uo_id, ativa=True)

        uas_qs = uas_qs.select_related("unidade_orcamentaria")
        uas_por_uo = {}
        for ua in uas_qs:
            uas_por_uo.setdefault(ua.unidade_orcamentaria_id, []).append(
                {
                    "id": ua.id,
                    "codigo": ua.codigo,
                    "nome": ua.nome,
                    "label": f"{ua.codigo} - {ua.nome}",
                    "unidade_administrativa_id": ua.id,
                    "unidade_orcamentaria_id": ua.unidade_orcamentaria_id,
                }
            )

        permite_uo = bool(obj.is_superuser or obj.is_gestor_patrimonio)
        grupos = []
        for uo in uos_qs:
            grupo = {
                "uo": {
                    "id": uo.id,
                    "codigo": uo.codigo,
                    "nome": uo.nome,
                    "label": f"{uo.codigo} - {uo.nome}",
                    "selecionavel": permite_uo,
                    "unidade_administrativa_id": None,
                    "unidade_orcamentaria_id": uo.id,
                },
                "uas": uas_por_uo.get(uo.id, []),
            }
            grupos.append(grupo)

        return {
            "grupos": grupos,
        }


def _validate_ua_selecionada(ua_id, uo_id):
    """Resolve e valida UA quando unidade_administrativa_id é informado. Retorna (ua, uo_id)."""
    try:
        ua = UnidadeAdministrativa.objects.select_related(
            "unidade_orcamentaria"
        ).get(id=ua_id)
    except UnidadeAdministrativa.DoesNotExist:
        raise serializers.ValidationError(
            {"unidade_administrativa_id": "Unidade Administrativa invalida."}
        )
    if ua.status != UnidadeAdministrativa.ATIVA:
        raise serializers.ValidationError(
            {"unidade_administrativa_id": "Unidade Administrativa inativa."}
        )
    if uo_id is not None and ua.unidade_orcamentaria_id != uo_id:
        raise serializers.ValidationError(
            {
                "unidade_orcamentaria_id": "Unidade Orcamentaria nao corresponde a Unidade Administrativa."
            }
        )
    return ua, ua.unidade_orcamentaria.id


def _validate_uo_sem_ua(user, uo_id):
    """Valida e resolve uo_id quando nenhuma UA é selecionada."""
    if user.is_operador_inventario and not user.is_superuser:
        raise serializers.ValidationError(
            "Operador nao pode selecionar Unidade Orcamentaria."
        )
    if uo_id is None:
        uo_id = obter_unidade_orcamentaria_id_do_usuario(user)
    if not uo_id:
        raise serializers.ValidationError(
            {"unidade_orcamentaria_id": "Unidade Orcamentaria obrigatoria."}
        )
    return uo_id


def _validate_permissoes_uo_ua(user, uo_id, ua):
    """Valida permissões de UO/UA para não-superusuários."""
    uo_usuario_id = obter_unidade_orcamentaria_id_do_usuario(user)
    if uo_usuario_id and uo_id != uo_usuario_id:
        raise serializers.ValidationError(
            "Usuario nao pode selecionar Unidade Orcamentaria diferente."
        )
    if (
        user.is_operador_inventario
        and ua
        and not user.unidades_administrativas.filter(id=ua.id).exists()
    ):
        raise serializers.ValidationError(
            "Operador so pode selecionar UAs atribuidas a ele."
        )
    if (
        user.is_gestor_patrimonio
        and ua
        and uo_usuario_id
        and ua.unidade_orcamentaria_id != uo_usuario_id
    ):
        raise serializers.ValidationError(
            "Gestor so pode selecionar UA da propria Unidade Orcamentaria."
        )


def _resolve_uo(uo_id):
    """Obtém UnidadeOrcamentaria por id e valida se está ativa."""
    try:
        uo = UnidadeOrcamentaria.objects.get(id=uo_id)
    except UnidadeOrcamentaria.DoesNotExist:
        raise serializers.ValidationError(
            {"unidade_orcamentaria_id": "Unidade Orcamentaria invalida."}
        )
    if not uo.ativa:
        raise serializers.ValidationError(
            {"unidade_orcamentaria_id": "Unidade Orcamentaria inativa."}
        )
    return uo


class SelecionarUnidadeAdministrativaSerializer(serializers.Serializer):
    unidade_administrativa_id = serializers.IntegerField(allow_null=True, required=True)
    unidade_orcamentaria_id = serializers.IntegerField(allow_null=True, required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Usuario nao autenticado.")

        ua_id = attrs.get("unidade_administrativa_id")
        uo_id = attrs.get("unidade_orcamentaria_id")
        ua = None
        uo = None

        if ua_id is not None:
            ua, uo_id = _validate_ua_selecionada(ua_id, uo_id)
            uo = ua.unidade_orcamentaria
        else:
            uo_id = _validate_uo_sem_ua(user, uo_id)

        if not user.is_superuser:
            _validate_permissoes_uo_ua(user, uo_id, ua)

        if uo is None:
            uo = _resolve_uo(uo_id)

        attrs["ua_obj"] = ua
        attrs["uo_obj"] = uo
        return attrs


class UsuarioSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True, required=False)
    password_confirm = serializers.CharField(write_only=True, required=False)

    group_name = serializers.CharField(write_only=True, required=False, allow_null=True)

    unidade_orcamentaria = serializers.PrimaryKeyRelatedField(
        queryset=UnidadeOrcamentaria.objects.all(),
        allow_null=True,
        required=False
    )

    unidade_administrativa = serializers.PrimaryKeyRelatedField(
        queryset=UnidadeAdministrativa.objects.all(),
        allow_null=True,
        required=False
    )

    unidades_administrativas = serializers.PrimaryKeyRelatedField(
        queryset=UnidadeAdministrativa.objects.all(),
        many=True,
        required=False
    )

    unidade_codigo = serializers.SerializerMethodField()
    unidade_nome = serializers.SerializerMethodField()
    grupo_nome = serializers.SerializerMethodField()

    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    is_gestor_patrimonio = serializers.BooleanField(read_only=True)
    is_operador_inventario = serializers.BooleanField(read_only=True)

    class Meta:
        model = User

        fields = [
            "id",
            "username",
            "email",
            "nome",
            "rf",
            "password",
            "password_confirm",
            "is_active",
            "group_name",
            "unidade_orcamentaria",
            "unidade_administrativa",
            "unidades_administrativas",
            "last_login",
            "date_joined",
            "unidade_codigo",
            "unidade_nome",
            "grupo_nome",
            "status",
            "status_display",
            "is_gestor_patrimonio",
            "is_operador_inventario",
        ]

        read_only_fields = [
            "id",
            "last_login",
            "date_joined",
            "last_password_change",
            "must_change_password",
            "is_gestor_patrimonio",
            "is_operador_inventario",
        ]

    def get_unidade_codigo(self, obj):
        if obj.unidade_administrativa:
            return obj.unidade_administrativa.codigo
        return None

    def get_unidade_nome(self, obj):
        if obj.unidade_administrativa:
            return obj.unidade_administrativa.nome
        return None

    def get_grupo_nome(self, obj):
        grupo = obj.groups.first()
        if grupo:
            return grupo.name
        return None

    def get_status(self, obj):
        return "ativo" if obj.is_active else "inativo"

    def get_status_display(self, obj):
        return "Ativo" if obj.is_active else "Inativo"

    def validate(self, attrs):

        request = self.context.get("request")
        user = request.user if request else None
        instance = getattr(self, "instance", None)

        raw = getattr(self, "initial_data", {})

        campos_sensiveis = {"is_superuser", "is_staff"}

        for campo in campos_sensiveis:
            if campo in raw:
                raise serializers.ValidationError(
                    {campo: f"O campo '{campo}' não pode ser manipulado via API."}
                )

        if raw.get("is_superuser"):
            raise serializers.ValidationError(
                "Superusuário não pode ser criado via API."
            )

        group_name = attrs.pop("group_name", None)

        if group_name is not None:

            if instance and user and instance == user:
                raise serializers.ValidationError(
                    "Você não pode alterar seu próprio grupo."
                )

            allowed_groups = {
                GRUPO_GESTOR_PATRIMONIO,
                GRUPO_OPERADOR_INVENTARIO,
            }

            if group_name not in allowed_groups:
                raise serializers.ValidationError(
                    {"group_name": f"Grupo '{group_name}' não permitido. "
                     f"Use: {', '.join(allowed_groups)}."}
                )

            try:
                resolved_group = Group.objects.get(name=group_name)
            except Group.DoesNotExist:
                raise serializers.ValidationError(
                    {"group_name": f"Grupo '{group_name}' não encontrado no sistema."}
                )

            attrs["groups"] = [resolved_group]

        if "groups" in raw and group_name is None:
            raise serializers.ValidationError(
                {"groups": "Use o campo 'group_name' para definir o grupo do usuário."}
            )

        groups = attrs.get("groups")
        unidade_orcamentaria = attrs.get("unidade_orcamentaria")
        unidade_administrativa = attrs.get("unidade_administrativa")

        if instance:
            if groups is None:
                groups = list(instance.groups.all())

            if unidade_orcamentaria is None:
                unidade_orcamentaria = instance.unidade_orcamentaria

            if unidade_administrativa is None:
                unidade_administrativa = instance.unidade_administrativa

        if unidade_administrativa and unidade_orcamentaria:
            if (
                unidade_administrativa.unidade_orcamentaria_id
                != unidade_orcamentaria.id
            ):
                raise serializers.ValidationError(
                    {
                        "unidade_administrativa":
                        "A Unidade Administrativa não pertence à Unidade Orçamentária informada."
                    }
                )

        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password:
            if password != password_confirm:
                raise serializers.ValidationError(
                    {"password": "As senhas não coincidem."}
                )

            if len(password) < 6:
                raise serializers.ValidationError(
                    {"password": "A senha deve possuir no mínimo 6 caracteres."}
                )

            if not re.search(r"[A-Za-z]", password):
                raise serializers.ValidationError(
                    {"password": "A senha deve conter letras."}
                )

            if not re.search(r"\d", password):
                raise serializers.ValidationError(
                    {"password": "A senha deve conter números."}
                )

            if not re.search(r"[^\w\s]", password):
                raise serializers.ValidationError(
                    {"password": "A senha deve conter caractere especial."}
                )

        if groups:
            group_names = {g.name for g in groups}

            if GRUPO_OPERADOR_INVENTARIO in group_names and not unidade_administrativa:
                raise serializers.ValidationError(
                    "Operador deve possuir unidade administrativa."
                )

            if GRUPO_GESTOR_PATRIMONIO in group_names and not unidade_orcamentaria:
                raise serializers.ValidationError(
                    "Gestor deve possuir unidade orçamentária."
                )

        return attrs

    def create(self, validated_data):

        password = validated_data.pop("password", None)
        validated_data.pop("password_confirm", None)

        unidades_administrativas = validated_data.pop("unidades_administrativas", [])
        groups = validated_data.pop("groups", [])

        validated_data["is_staff"] = True
        validated_data["is_superuser"] = False

        user = User(**validated_data)

        if password:
            user.set_password(password)

        user.save()

        if unidades_administrativas:
            user.unidades_administrativas.set(unidades_administrativas)

        if groups:
            user.groups.set(groups)

        return user

    def update(self, instance, validated_data):

        password = validated_data.pop("password", None)
        validated_data.pop("password_confirm", None)

        unidades_administrativas = validated_data.pop("unidades_administrativas", None)
        groups = validated_data.pop("groups", None)

        validated_data.pop("is_staff", None)
        validated_data.pop("is_superuser", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        if unidades_administrativas is not None:
            instance.unidades_administrativas.set(unidades_administrativas)

        if groups is not None:
            instance.groups.set(groups)

        return instance
