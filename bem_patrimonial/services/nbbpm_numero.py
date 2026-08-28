import re
import logging

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import IntegerField, Max, Q, Value
from django.db.models.functions import Cast, Replace, Substr
from django.utils import timezone

logger = logging.getLogger(__name__)

PREFIXO_FIXO = "001"
# Novo formato: 001.0000001/2026  (mantém compatibilidade com antigo 001.0000001.2026 para números já existentes)
NBBPM_REGEX = r"^\d{3}\.\d{7}[\./]\d{4}$"


def _max_sequencial_nbbpm_por_ano(ano: int):
    """MAX sequencial existente em NBBPM para prefixo fixo 001/ano (considera . e /)."""
    from bem_patrimonial.models import NBBPM

    qs = (
        NBBPM.objects.filter(
            numero__startswith=f"{PREFIXO_FIXO}.",
            numero__isnull=False,
        )
        .exclude(numero__exact="")
        .exclude(numero__exact=None)
        .filter(Q(numero__endswith=f".{ano}") | Q(numero__endswith=f"/{ano}"))
    )
    sequencial_raw = Substr("numero", 5, 7)
    sequencial_digits = Replace(sequencial_raw, Value("."), Value(""))
    # também remove "/" caso exista no slice (não deve, mas garante)
    sequencial_digits = Replace(sequencial_digits, Value("/"), Value(""))
    result = qs.annotate(sequencial_int=Cast(sequencial_digits, IntegerField())).aggregate(
        max_seq=Max("sequencial_int")
    )
    return result["max_seq"] or 0


def _max_sequencial_baixa_legado_por_ano(ano: int):
    """MAX sequencial do legado Baixa.numero_nbbpm para prefixo fixo 001/ano."""
    from bem_patrimonial.models import BaixaFisicaBemPatrimonial

    qs = (
        BaixaFisicaBemPatrimonial.objects.filter(
            numero_nbbpm__startswith=f"{PREFIXO_FIXO}.",
            numero_nbbpm__isnull=False,
        )
        .exclude(numero_nbbpm__exact="")
        .filter(Q(numero_nbbpm__endswith=f".{ano}") | Q(numero_nbbpm__endswith=f"/{ano}"))
    )
    sequencial_raw = Substr("numero_nbbpm", 5, 7)
    sequencial_digits = Replace(sequencial_raw, Value("."), Value(""))
    sequencial_digits = Replace(sequencial_digits, Value("/"), Value(""))
    result = qs.annotate(sequencial_int=Cast(sequencial_digits, IntegerField())).aggregate(
        max_seq=Max("sequencial_int")
    )
    return result["max_seq"] or 0


def obter_proximo_sequencial_por_ano(ano: int) -> int:
    """Próximo sequencial global para prefixo 001/ano."""
    max_nbbpm = _max_sequencial_nbbpm_por_ano(ano)
    max_baixa = _max_sequencial_baixa_legado_por_ano(ano)
    maior = max(max_nbbpm, max_baixa)
    return maior + 1


def _extrair_ano_nbbpm(nbbpm):
    if getattr(nbbpm, "data_autorizacao", None):
        return nbbpm.data_autorizacao.year
    data_aprov = getattr(nbbpm, "data_aprovacao", None)
    if data_aprov:
        try:
            return data_aprov.year if hasattr(data_aprov, "year") else int(str(data_aprov)[:4])
        except Exception:
            return None
    return None


def _gerar_numero_formatado(ano: int) -> str:
    proximo = obter_proximo_sequencial_por_ano(ano)
    numero = f"{PREFIXO_FIXO}.{proximo:07d}/{ano}"
    if not re.fullmatch(NBBPM_REGEX, numero):
        raise ValidationError(f"Número gerado inválido: {numero}")
    return numero


def gerar_numero_nbbpm_unificado(nbbpm, max_tentativas: int = 3):
    """Gera número NBBPM 001.YYYYYYY/ZZZZ com prefixo fixo 001 e sequencial global por ano."""
    from bem_patrimonial.models import NBBPM

    if not isinstance(nbbpm, NBBPM):
        raise ValidationError("Objeto inválido para geração de NBBPM.")
    ano = _extrair_ano_nbbpm(nbbpm) or timezone.localdate().year
    return _tentar_gerar_numero(ano, max_tentativas)


def _tentar_gerar_numero(ano: int, max_tentativas: int):
    last_exc = None
    for tentativa in range(max_tentativas):
        try:
            with transaction.atomic():
                return _gerar_numero_formatado(ano)
        except IntegrityError as exc:
            last_exc = exc
            logger.warning(
                "Conflito UNIQUE ao gerar NBBPM %s/%s tentativa %s: %s",
                PREFIXO_FIXO,
                ano,
                tentativa + 1,
                exc,
            )
            if tentativa == max_tentativas - 1:
                raise
    if last_exc:
        raise last_exc
    raise ValidationError("Falha ao gerar número NBBPM após tentativas.")


def gerar_numero_para_ano(ano: int, max_tentativas: int = 3) -> str:
    """Gera número diretamente a partir de ano (prefixo fixo 001)."""
    return _tentar_gerar_numero(ano, max_tentativas)


def _validar_uo_baixas(baixas):
    uo_ids = set()
    for baixa in baixas:
        ua = getattr(baixa, "unidade_administrativa_origem", None)
        if not ua or not getattr(ua, "pk", None):
            raise ValidationError(f"Baixa {getattr(baixa, 'pk', '?')} sem Unidade Administrativa.")
        uo_id = getattr(ua, "unidade_orcamentaria_id", None)
        if uo_id is None:
            try:
                uo_id = getattr(ua.unidade_orcamentaria, "pk", None) if getattr(ua, "unidade_orcamentaria", None) else None
            except Exception:
                uo_id = None
        uo_ids.add(uo_id)
    if len(uo_ids) > 1 or None in uo_ids:
        raise ValidationError("Todas as Baixas selecionadas devem pertencer à mesma Unidade Orçamentária.")
    return uo_ids


def _validar_bloqueio_baixas(locked_baixas):
    for baixa in locked_baixas:
        if baixa.nbbpms_lote.exists():
            raise ValidationError(f"Baixa {baixa.pk} já possui NBBPM gerada.")
        if getattr(baixa, "numero_nbbpm", None):
            raise ValidationError(f"Baixa {baixa.pk} já possui número legado e não pode ser reutilizada.")


def _validar_uo_locked(locked_baixas):
    uo_ids_locked = {
        getattr(getattr(lb, "unidade_administrativa_origem", None), "unidade_orcamentaria_id", None)
        for lb in locked_baixas
    }
    if len(uo_ids_locked) > 1 or None in uo_ids_locked:
        raise ValidationError("Todas as Baixas selecionadas devem pertencer à mesma Unidade Orçamentária.")


def _criar_nbbpm_atomico(baixas, numero_processo_baixa, data_autorizacao, responsavel, criado_por, numero_processo_destinacao_final, ano, uo_ids, tentativa):
    from bem_patrimonial.models import NBBPM, BaixaFisicaBemPatrimonial

    baixa_ids = [b.pk for b in baixas]
    locked = list(BaixaFisicaBemPatrimonial.objects.select_for_update().filter(pk__in=baixa_ids))
    for lb in locked:
        try:
            _ = lb.unidade_administrativa_origem
            _ = lb.unidade_administrativa_origem.unidade_orcamentaria_id if lb.unidade_administrativa_origem else None
        except Exception:
            pass
    _validar_bloqueio_baixas(locked)
    _validar_uo_locked(locked)
    numero = _gerar_numero_formatado(ano)
    nbbpm = NBBPM.objects.create(
        numero=numero,
        numero_processo_baixa=numero_processo_baixa,
        data_autorizacao=data_autorizacao,
        responsavel=responsavel,
        numero_processo_destinacao_final=numero_processo_destinacao_final or "",
        criado_por=criado_por,
    )
    nbbpm.baixas.set(locked)
    logger.info("NBBPM gerada %s %s tentativa %s", PREFIXO_FIXO, numero, tentativa)
    _registrar_historico_nbbpm(nbbpm, criado_por, uo_ids, ano, locked)
    return nbbpm


def _registrar_historico_nbbpm(nbbpm, criado_por, uo_ids, ano, locked):
    try:
        from dados_comuns.models import HistoricoGeral
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(nbbpm.__class__)
        HistoricoGeral.objects.create(
            content_type=ct,
            object_id=str(nbbpm.pk),
            campo="numero",
            valor_antigo="",
            valor_novo=nbbpm.numero,
            alterado_por=criado_por,
            justificativa=f"NBBPM {nbbpm.numero} gerada UO {list(uo_ids)[0]} ano {ano} com {len(locked)} baixa(s)",
        )
    except Exception:
        pass


def criar_nbbpm_com_retry(*, baixas, numero_processo_baixa, data_autorizacao, responsavel, criado_por, numero_processo_destinacao_final="", max_tentativas=3):
    """Cria NBBPM com select_for_update e retry em IntegrityError. Sequencial global por ano, escopo por UO."""
    if not baixas:
        raise ValidationError("Selecione ao menos uma Baixa.")
    primeira = baixas[0]
    primeira_ua = getattr(primeira, "unidade_administrativa_origem", None)
    if not primeira_ua or not getattr(primeira_ua, "pk", None):
        raise ValidationError("Unidade Administrativa não encontrada para as baixas.")
    uo_ids = _validar_uo_baixas(baixas)
    ano = data_autorizacao.year if hasattr(data_autorizacao, "year") else timezone.localdate().year
    for tentativa in range(max_tentativas):
        try:
            with transaction.atomic():
                return _criar_nbbpm_atomico(
                    baixas, numero_processo_baixa, data_autorizacao, responsavel, criado_por, numero_processo_destinacao_final, ano, uo_ids, tentativa + 1
                )
        except IntegrityError as exc:
            logger.warning(
                "IntegrityError ao criar NBBPM %s/%s tentativa %s: %s",
                PREFIXO_FIXO,
                ano,
                tentativa + 1,
                exc,
            )
            if tentativa == max_tentativas - 1:
                raise ValidationError("Falha de concorrência ao gerar NBBPM, tente novamente.")
            continue
    raise ValidationError("Falha ao criar NBBPM após tentativas.")
