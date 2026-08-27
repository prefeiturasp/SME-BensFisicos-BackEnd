import re
import logging

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import IntegerField, Max, Value
from django.db.models.functions import Cast, Replace, Substr
from django.utils import timezone

logger = logging.getLogger(__name__)

NBBPM_REGEX = r"^\d{3}\.\d{7}\.\d{4}$"


def extrair_codigo_ua(codigo_completo):
    """Extrai prefixo UA (3 dígitos) — último grupo. Ex.: '01.16.10.287' -> '287'."""
    apenas_numeros = re.sub(r"\D", "", str(codigo_completo or ""))
    if not apenas_numeros:
        return "000"
    if "." in str(codigo_completo):
        ultimo_grupo = str(codigo_completo).split(".")[-1]
        ultimo_numero = re.sub(r"\D", "", ultimo_grupo).lstrip("0") or "0"
    else:
        ultimo_numero = apenas_numeros.lstrip("0") or "0"
    return ultimo_numero.zfill(3)[-3:]


def _max_sequencial_nbbpm_por_ua_ano(prefixo_ua: str, ano: int):
    """MAX sequencial existente em NBBPM para prefixo UA/ano."""
    from bem_patrimonial.models import NBBPM

    qs = (
        NBBPM.objects.filter(
            numero__startswith=f"{prefixo_ua}.",
            numero__endswith=f".{ano}",
            numero__isnull=False,
        )
        .exclude(numero__exact="")
        .exclude(numero__exact=None)
    )
    sequencial_raw = Substr("numero", 5, 7)
    sequencial_digits = Replace(sequencial_raw, Value("."), Value(""))
    result = qs.annotate(sequencial_int=Cast(sequencial_digits, IntegerField())).aggregate(
        max_seq=Max("sequencial_int")
    )
    return result["max_seq"] or 0


def _max_sequencial_baixa_legado_por_ua_ano(ua, ano: int):
    """MAX sequencial do legado Baixa.numero_nbbpm para UA/ano."""
    from bem_patrimonial.models import BaixaFisicaBemPatrimonial

    if ua is None or not getattr(ua, "pk", None):
        return 0
    qs = (
        BaixaFisicaBemPatrimonial.objects.filter(
            unidade_administrativa_origem_id=ua.pk,
            numero_nbbpm__isnull=False,
        )
        .exclude(numero_nbbpm__exact="")
        .filter(numero_nbbpm__endswith=f".{ano}")
    )
    sequencial_raw = Substr("numero_nbbpm", 5, 7)
    sequencial_digits = Replace(sequencial_raw, Value("."), Value(""))
    result = qs.annotate(sequencial_int=Cast(sequencial_digits, IntegerField())).aggregate(
        max_seq=Max("sequencial_int")
    )
    return result["max_seq"] or 0


def obter_proximo_sequencial_por_ua_ano(ua, prefixo_ua: str, ano: int) -> int:
    """Próximo sequencial considerando NBBPM e legado."""
    max_nbbpm = _max_sequencial_nbbpm_por_ua_ano(prefixo_ua, ano)
    max_baixa = _max_sequencial_baixa_legado_por_ua_ano(ua, ano)
    maior = max(max_nbbpm, max_baixa)
    return maior + 1


def gerar_numero_nbbpm_unificado(nbbpm, max_tentativas: int = 3):
    """Gera número NBBPM XXX.YYYYYYY.ZZZZ com prefixo UA e sequencial por UA/ano."""
    from bem_patrimonial.models import NBBPM

    if not isinstance(nbbpm, NBBPM):
        raise ValidationError("Objeto inválido para geração de NBBPM.")

    ano = None
    if getattr(nbbpm, "data_autorizacao", None):
        ano = nbbpm.data_autorizacao.year
    else:
        data_aprov = getattr(nbbpm, "data_aprovacao", None)
        if data_aprov:
            try:
                ano = data_aprov.year if hasattr(data_aprov, "year") else int(str(data_aprov)[:4])
            except Exception:
                ano = None
    if not ano:
        ano = timezone.localdate().year

    ua = None
    try:
        primeira = nbbpm.baixas.select_related("unidade_administrativa_origem").first()
        if primeira:
            ua = getattr(primeira, "unidade_administrativa_origem", None)
    except Exception:
        pass
    # fallback legacy property unidade_orcamentaria -> resolve UA via property
    if ua is None:
        ua = getattr(nbbpm, "unidade_administrativa_origem", None)

    codigo_ua = getattr(ua, "codigo", "") if ua else ""
    prefixo_ua = extrair_codigo_ua(codigo_ua)

    last_exc = None
    for tentativa in range(max_tentativas):
        try:
            with transaction.atomic():
                proximo = obter_proximo_sequencial_por_ua_ano(ua, prefixo_ua, ano)
                numero = f"{prefixo_ua}.{proximo:07d}.{ano}"
                if not re.fullmatch(NBBPM_REGEX, numero):
                    raise ValidationError(f"Número gerado inválido: {numero}")
                return numero
        except IntegrityError as e:
            last_exc = e
            logger.warning(
                "Conflito UNIQUE ao gerar NBBPM %s/%s tentativa %s: %s",
                prefixo_ua,
                ano,
                tentativa + 1,
                e,
            )
            if tentativa == max_tentativas - 1:
                raise
            continue
    if last_exc:
        raise last_exc
    raise ValidationError("Falha ao gerar número NBBPM após tentativas.")


def gerar_numero_para_ua_ano(ua, ano: int, max_tentativas: int = 3) -> str:
    """Gera número diretamente a partir de UA/ano sem instância completa."""
    prefixo_ua = extrair_codigo_ua(getattr(ua, "codigo", "") if ua else "")
    for tentativa in range(max_tentativas):
        try:
            with transaction.atomic():
                proximo = obter_proximo_sequencial_por_ua_ano(ua, prefixo_ua, ano)
                numero = f"{prefixo_ua}.{proximo:07d}.{ano}"
                if not re.fullmatch(NBBPM_REGEX, numero):
                    raise ValidationError(f"Número gerado inválido: {numero}")
                return numero
        except IntegrityError:
            if tentativa == max_tentativas - 1:
                raise
            continue
    raise ValidationError("Falha ao gerar número para UA/ano")


def criar_nbbpm_com_retry(*, baixas, numero_processo_baixa, data_autorizacao, responsavel, criado_por, numero_processo_destinacao_final="", max_tentativas=3):
    """Cria NBBPM com select_for_update e retry em IntegrityError. Sequencial por UA/ano."""
    from bem_patrimonial.models import NBBPM, BaixaFisicaBemPatrimonial

    if not baixas:
        raise ValidationError("Selecione ao menos uma Baixa.")

    first_ua = baixas[0].unidade_administrativa_origem
    if not first_ua or not getattr(first_ua, "pk", None):
        raise ValidationError("Unidade Administrativa não encontrada para as baixas.")

    # valida mesma UA
    ua_ids = {getattr(b.unidade_administrativa_origem, "pk", None) for b in baixas}
    if len(ua_ids) > 1:
        raise ValidationError("Todas as Baixas selecionadas devem pertencer à mesma Unidade Administrativa.")

    ano = data_autorizacao.year if hasattr(data_autorizacao, "year") else timezone.localdate().year
    prefixo_ua = extrair_codigo_ua(getattr(first_ua, "codigo", ""))

    for tentativa in range(max_tentativas):
        try:
            with transaction.atomic():
                baixa_ids = [b.pk for b in baixas]
                locked_baixas = list(
                    BaixaFisicaBemPatrimonial.objects.select_for_update().filter(pk__in=baixa_ids)
                )
                for lb in locked_baixas:
                    if lb.nbbpms_lote.exists():
                        raise ValidationError(f"Baixa {lb.pk} já possui NBBPM gerada.")
                    if getattr(lb, "numero_nbbpm", None):
                        raise ValidationError(f"Baixa {lb.pk} já possui número legado e não pode ser reutilizada.")

                proximo = obter_proximo_sequencial_por_ua_ano(first_ua, prefixo_ua, ano)
                numero = f"{prefixo_ua}.{proximo:07d}.{ano}"
                if not re.fullmatch(NBBPM_REGEX, numero):
                    raise ValidationError(f"Número gerado inválido: {numero}")

                nbbpm = NBBPM.objects.create(
                    numero=numero,
                    numero_processo_baixa=numero_processo_baixa,
                    data_autorizacao=data_autorizacao,
                    responsavel=responsavel,
                    numero_processo_destinacao_final=numero_processo_destinacao_final or "",
                    criado_por=criado_por,
                )
                nbbpm.baixas.set(locked_baixas)
                logger.info("NBBPM gerada %s %s tentativa %s", prefixo_ua, numero, tentativa + 1)
                try:
                    from dados_comuns.models import HistoricoGeral
                    from django.contrib.contenttypes.models import ContentType
                    ct = ContentType.objects.get_for_model(NBBPM)
                    HistoricoGeral.objects.create(
                        content_type=ct,
                        object_id=str(nbbpm.pk),
                        campo="numero",
                        valor_antigo="",
                        valor_novo=nbbpm.numero,
                        alterado_por=criado_por,
                        justificativa=f"NBBPM {nbbpm.numero} gerada UA {prefixo_ua} ano {ano} com {len(locked_baixas)} baixa(s)",
                    )
                except Exception:
                    pass
                return nbbpm
        except IntegrityError as e:
            logger.warning(
                "IntegrityError ao criar NBBPM %s/%s tentativa %s: %s",
                prefixo_ua,
                ano,
                tentativa + 1,
                e,
            )
            if tentativa == max_tentativas - 1:
                raise ValidationError("Falha de concorrência ao gerar NBBPM, tente novamente.")
            continue
    raise ValidationError("Falha ao criar NBBPM após tentativas.")
