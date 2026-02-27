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


class Command(BaseCommand):
    help = "Cria 2 UnidadesAdministrativas e 2 BemPatrimonial por UA (mínimo, tipos corretos), desativando signals."

    def handle(self, *args, **options):
        # ===== Models =====
        UA = get_model("dados_comuns.UnidadeAdministrativa")
        bem_model = get_model("bem_patrimonial.BemPatrimonial")
        through_model = None  # get_model("bem_patrimonial.UnidadeAdministrativaBemPatrimonial") quando existir

        if not UA or not bem_model:
            raise CommandError(
                "Model não encontrado: dados_comuns.UnidadeAdministrativa e/ou bem_patrimonial.BemPatrimonial."
            )

        # ===== User p/ FKs de autor, se existirem =====
        user_model = get_user_model()
        system_user, _ = user_model.objects.get_or_create(
            username="sistema_seed",
            defaults={
                "email": "seed@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )

        # ===== Tentar importar o receiver do signal para desconectar com segurança =====
        receiver_func = None
        try:
            from bem_patrimonial.models import (
                cria_registro_unidade_administrativa_bem_patrimonial as receiver_func,
            )  # noqa: F401
        except Exception:
            receiver_func = (
                None  # se não existir, seguimos sem desconectar nominalmente
            )

        # ===== Desconectar signal (se conhecido) =====
        if receiver_func is not None:
            try:
                post_save.disconnect(receiver=receiver_func, sender=bem_model)
            except Exception:
                pass

        today = timezone.now().date()
        now = timezone.now()

        # ===== Limpar minimamente (opcional; comente se não quiser limpar) =====
        if through_model:
            through_model.objects.all().delete()
        bem_model.objects.all().delete()
        UA.objects.all().delete()

        # ===== Criar 2 UAs só com campos existentes =====
        uas = []
        with transaction.atomic():
            for i in range(1, 3):
                ua_payload = {}
                # Preenche apenas o que existir no seu model
                if has_field(UA, "nome"):
                    ua_payload["nome"] = f"Unidade Administrativa {i}"
                if has_field(UA, "sigla"):
                    ua_payload["sigla"] = f"UA{i:02d}"
                if has_field(UA, "descricao"):
                    ua_payload["descricao"] = f"UA {i:02d}"
                if has_field(UA, "codigo"):
                    ua_payload["codigo"] = 100 + i
                # Adicione aqui mais campos que seu model exija como NOT NULL, se houver

                ua = UA.objects.create(**ua_payload)
                uas.append(ua)

        self.stdout.write(self.style.SUCCESS("✔ Criadas 2 UnidadesAdministrativas"))

        # ===== Mapear FKs e campos para Bem e Through =====
        fk_bem_ua = first_fk_to(bem_model, UA) or (
            has_field(bem_model, "unidade_administrativa") and "unidade_administrativa"
        )
        fk_through_bem = (
            first_fk_to(through_model, bem_model) if through_model else None
        )
        fk_through_ua = first_fk_to(through_model, UA) if through_model else None

        # Campos de autor em Bem (se existirem com esses nomes comuns)
        author_field_in_bem = None
        for name in ("criado_por", "created_by", "usuario"):
            if has_field(bem_model, name):
                author_field_in_bem = name
                break

        # ===== Criar 2 Bens por UA com tipos corretos =====
        for idx_ua, ua in enumerate(uas, start=1):
            for i in range(1, 3):
                seq = 100000 + idx_ua * 100 + i  # inteiro único e estável
                bem_kwargs = {}

                # Identificação textual (se existir)
                if has_field(bem_model, "descricao"):
                    bem_kwargs["descricao"] = f"Bem UA{idx_ua:02d} #{i:02d}"
                if has_field(bem_model, "titulo"):
                    bem_kwargs.setdefault("titulo", f"Bem UA{idx_ua:02d} #{i:02d}")

                # Inteiros/IDs obrigatórios (tipos numéricos!)
                if has_field(bem_model, "numero_tombo"):
                    bem_kwargs["numero_tombo"] = seq
                if has_field(bem_model, "numero_serie"):
                    bem_kwargs["numero_serie"] = seq
                if has_field(bem_model, "numero_processo"):
                    bem_kwargs["numero_processo"] = seq

                # Datas
                if has_field(bem_model, "data_compra_entrega"):
                    bem_kwargs["data_compra_entrega"] = today
                if has_field(bem_model, "data_aquisicao"):
                    bem_kwargs.setdefault("data_aquisicao", today)
                if has_field(bem_model, "data_compra"):
                    bem_kwargs.setdefault("data_compra", today)
                if has_field(bem_model, "data_registro"):
                    bem_kwargs.setdefault("data_registro", now)

                # Decimais/valores/quantidade
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

                # Documentais (geralmente CharField)
                if has_field(bem_model, "nota_fiscal"):
                    bem_kwargs.setdefault("nota_fiscal", f"NF-{idx_ua:02d}{i:02d}")
                if has_field(bem_model, "numero_empenho"):
                    bem_kwargs.setdefault("numero_empenho", f"EMP-{idx_ua:02d}{i:02d}")

                # Status textual (se existir)
                for alt in ("status_atual", "situacao", "situacao_atual", "status"):
                    if has_field(bem_model, alt) and alt not in bem_kwargs:
                        bem_kwargs[alt] = "aguardando_aprovacao"

                # FK da UA (respeita se é field ou FK de nome diferente)
                if isinstance(fk_bem_ua, models.ForeignKey):
                    bem_kwargs[fk_bem_ua.name] = ua
                elif fk_bem_ua == "unidade_administrativa":
                    bem_kwargs["unidade_administrativa"] = ua
                else:
                    # tentativa final: encontrar qualquer FK para UA
                    any_fk = first_fk_to(bem_model, UA)
                    if any_fk:
                        bem_kwargs[any_fk.name] = ua

                # Autor/criador
                if author_field_in_bem:
                    bem_kwargs[author_field_in_bem] = system_user

                # Criar Bem
                with transaction.atomic():
                    bem = bem_model.objects.create(**bem_kwargs)

                # Criar vínculo Through explicitamente (sem depender do signal)
                if through_model and fk_through_bem and fk_through_ua:
                    t_kwargs = {
                        fk_through_bem.name: bem,
                        fk_through_ua.name: ua,
                    }
                    if has_field(through_model, "data"):
                        t_kwargs["data"] = now
                    elif has_field(through_model, "data_vinculo"):
                        t_kwargs["data_vinculo"] = now
                    if has_field(through_model, "descricao"):
                        t_kwargs["descricao"] = f"Vínculo UA{idx_ua:02d}-Bem{i:02d}"
                    through_model.objects.create(**t_kwargs)

        self.stdout.write(self.style.SUCCESS("✔ Criados 4 BemPatrimonial (2 por UA)"))
        self.stdout.write(self.style.SUCCESS("🏁 Seed mínimo concluído."))

        # ===== Reativar signal (se conhecíamos o receiver) =====
        if receiver_func is not None:
            try:
                post_save.connect(receiver=receiver_func, sender=bem_model)
            except Exception:
                pass
