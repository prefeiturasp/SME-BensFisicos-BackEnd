from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import transaction, models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save


def get_model(label: str):
    try:
        return apps.get_model(label)
    except Exception:
        return None


def has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


def first_fk_to(model, target_model):
    if not (model and target_model):
        return None
    for f in model._meta.get_fields():
        if isinstance(f, models.ForeignKey) and f.remote_field.model == target_model:
            return f
    return None


def _get_receiver_func():
    try:
        from bem_patrimonial.models import (
            cria_registro_unidade_administrativa_bem_patrimonial as receiver_func,
        )  # noqa: F401
        return receiver_func
    except Exception:
        return None


def _build_ua_payload(ua_model, i):
    payload = {}
    if has_field(ua_model, "nome"):
        payload["nome"] = f"Unidade Administrativa {i}"
    if has_field(ua_model, "sigla"):
        payload["sigla"] = f"UA{i:02d}"
    if has_field(ua_model, "descricao"):
        payload["descricao"] = f"UA {i:02d}"
    if has_field(ua_model, "codigo"):
        payload["codigo"] = 100 + i
    return payload


def _build_bem_kwargs(bem_model, ua_model, ua, idx_ua, i, today, now, fk_bem_ua, author_field_in_bem, system_user):
    seq = 100000 + idx_ua * 100 + i
    bem_kwargs = {}
    if has_field(bem_model, "descricao"):
        bem_kwargs["descricao"] = f"Bem UA{idx_ua:02d} #{i:02d}"
    if has_field(bem_model, "titulo"):
        bem_kwargs.setdefault("titulo", f"Bem UA{idx_ua:02d} #{i:02d}")
    if has_field(bem_model, "numero_tombo"):
        bem_kwargs["numero_tombo"] = seq
    if has_field(bem_model, "numero_serie"):
        bem_kwargs["numero_serie"] = seq
    if has_field(bem_model, "numero_processo"):
        bem_kwargs["numero_processo"] = seq
    if has_field(bem_model, "data_compra_entrega"):
        bem_kwargs["data_compra_entrega"] = today
    if has_field(bem_model, "data_aquisicao"):
        bem_kwargs.setdefault("data_aquisicao", today)
    if has_field(bem_model, "data_compra"):
        bem_kwargs.setdefault("data_compra", today)
    if has_field(bem_model, "data_registro"):
        bem_kwargs.setdefault("data_registro", now)
    if has_field(bem_model, "valor_unitario"):
        bem_kwargs["valor_unitario"] = Decimal("1000.00")
    if has_field(bem_model, "quantidade"):
        bem_kwargs["quantidade"] = 1
    if has_field(bem_model, "valor_aquisicao"):
        bem_kwargs.setdefault("valor_aquisicao", Decimal("1000.00"))
    if has_field(bem_model, "valor_compra"):
        bem_kwargs.setdefault("valor_compra", Decimal("1000.00"))
    if has_field(bem_model, "valor"):
        bem_kwargs.setdefault("valor", Decimal("1000.00"))
    if has_field(bem_model, "nota_fiscal"):
        bem_kwargs.setdefault("nota_fiscal", f"NF-{idx_ua:02d}{i:02d}")
    if has_field(bem_model, "numero_empenho"):
        bem_kwargs.setdefault("numero_empenho", f"EMP-{idx_ua:02d}{i:02d}")
    for alt in ("status_atual", "situacao", "situacao_atual", "status"):
        if has_field(bem_model, alt) and alt not in bem_kwargs:
            bem_kwargs[alt] = "aguardando_aprovacao"
    if isinstance(fk_bem_ua, models.ForeignKey):
        bem_kwargs[fk_bem_ua.name] = ua
    elif fk_bem_ua == "unidade_administrativa":
        bem_kwargs["unidade_administrativa"] = ua
    else:
        any_fk = first_fk_to(bem_model, ua_model)
        if any_fk:
            bem_kwargs[any_fk.name] = ua
    if author_field_in_bem:
        bem_kwargs[author_field_in_bem] = system_user
    return bem_kwargs


def _create_through_if_needed(through_model, bem, ua, idx_ua, i, now, fk_through_bem, fk_through_ua):
    if not through_model or not fk_through_bem or not fk_through_ua:
        return
    t_kwargs = {fk_through_bem.name: bem, fk_through_ua.name: ua}
    if has_field(through_model, "data"):
        t_kwargs["data"] = now
    elif has_field(through_model, "data_vinculo"):
        t_kwargs["data_vinculo"] = now
    if has_field(through_model, "descricao"):
        t_kwargs["descricao"] = f"Vínculo UA{idx_ua:02d}-Bem{i:02d}"
    through_model.objects.create(**t_kwargs)


class Command(BaseCommand):
    help = "Cria 2 UnidadesAdministrativas e 2 BemPatrimonial por UA (mínimo, tipos corretos), desativando signals."

    def handle(self, *args, **options):
        UA = get_model("dados_comuns.UnidadeAdministrativa")
        bem_model = get_model("bem_patrimonial.BemPatrimonial")
        through_model = None

        if not UA or not bem_model:
            raise CommandError(
                "Model não encontrado: dados_comuns.UnidadeAdministrativa e/ou bem_patrimonial.BemPatrimonial."
            )

        user_model = get_user_model()
        system_user, _ = user_model.objects.get_or_create(
            username="sistema_seed",
            defaults={"email": "seed@example.com", "is_staff": True, "is_superuser": True},
        )

        receiver_func = _get_receiver_func()
        if receiver_func is not None:
            try:
                post_save.disconnect(receiver=receiver_func, sender=bem_model)
            except Exception:
                pass

        today = timezone.now().date()
        now = timezone.now()

        if through_model:
            through_model.objects.all().delete()
        bem_model.objects.all().delete()
        UA.objects.all().delete()

        uas = self._create_uas(UA)
        self.stdout.write(self.style.SUCCESS("✔ Criadas 2 UnidadesAdministrativas"))

        fk_bem_ua = first_fk_to(bem_model, UA) or (
            has_field(bem_model, "unidade_administrativa") and "unidade_administrativa"
        )
        fk_through_bem = first_fk_to(through_model, bem_model) if through_model else None
        fk_through_ua = first_fk_to(through_model, UA) if through_model else None

        author_field_in_bem = None
        for name in ("criado_por", "created_by", "usuario"):
            if has_field(bem_model, name):
                author_field_in_bem = name
                break

        for idx_ua, ua in enumerate(uas, start=1):
            for i in range(1, 3):
                bem_kwargs = _build_bem_kwargs(
                    bem_model, UA, ua, idx_ua, i, today, now,
                    fk_bem_ua, author_field_in_bem, system_user,
                )
                with transaction.atomic():
                    bem = bem_model.objects.create(**bem_kwargs)
                _create_through_if_needed(
                    through_model, bem, ua, idx_ua, i, now,
                    fk_through_bem, fk_through_ua,
                )

        self.stdout.write(self.style.SUCCESS("✔ Criados 4 BemPatrimonial (2 por UA)"))
        self.stdout.write(self.style.SUCCESS("🏁 Seed mínimo concluído."))

        if receiver_func is not None:
            try:
                post_save.connect(receiver=receiver_func, sender=bem_model)
            except Exception:
                pass

    def _create_uas(self, UA):
        uas = []
        with transaction.atomic():
            for i in range(1, 3):
                ua_payload = _build_ua_payload(UA, i)
                ua = UA.objects.create(**ua_payload)
                uas.append(ua)
        return uas
