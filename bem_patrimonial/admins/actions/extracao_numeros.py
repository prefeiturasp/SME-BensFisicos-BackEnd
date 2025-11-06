from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponse
import re, csv
from django.template.response import TemplateResponse
from django.contrib.admin import helpers
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from collections import Counter


NEW_PATTERN_STRICT = re.compile(r"^\d{3}\.\d{9}-\d$")
ALPHA_RE = re.compile(r"[A-Za-zÁ-ú]")


def _digits_only(s: str) -> str:
    import re

    return re.sub(r"\D", "", s or "")


def _coerce_to_new(num_like: str):
    """
    Remove não-numéricos; se sobrar 13 dígitos (3+9+1),
    formata para 000.000000000-0 e retorna.
    (Obs.: 14 dígitos NÃO é aceito pelo model — será 'PADRAO_ANTERIOR')
    """
    d = _digits_only(num_like)
    if len(d) == 13:
        return f"{d[:3]}.{d[3:12]}-{d[12:]}"
    return None


def _first_token(text: str):
    """
    Token inicial até espaço ' ' ou '/' (remove '/' final). Mantém pontos/hífens internos.
    Ex.: '001050761830-0 ARMÁRIO' -> '001050761830-0'
         '001.050...-3/ mesa'     -> '001.050...-3'
    """
    t = (text or "").lstrip()
    if not t:
        return None, None, None
    end = len(t)
    for i, ch in enumerate(t):
        if ch == " " or ch == "/":
            end = i
            break
    tok = t[:end].rstrip("/").strip()
    return (tok if tok else None, 0 if tok else None, end)


def _last_numericish_token(text: str):
    """
    Captura token 'numérico-ish' no fim: dígitos, pontos, hífens, espaços, '/'; termina em dígito.
    Rejeita se contiver letras.
    """
    base = (text or "").strip()
    if not base:
        return None, None, None
    m = re.search(r"([0-9][0-9\.\-\s/]*[0-9])\s*$", base)
    if not m:
        return None, None, None
    tok = m.group(1).rstrip("/").strip()
    if not tok or ALPHA_RE.search(tok):
        return None, None, None
    start = m.start(1)
    end = m.end(1)
    return tok, start, end


def _classify_token(token: str):
    """
    Retorna (classificacao, valor_normalizado_ou_token) COM APENAS 3 ESTADOS:
    - PADRAO_ATUAL       -> bate NEW_PATTERN_STRICT ou foi coerção 13 dígitos
    - PADRAO_ANTERIOR    -> caso contrário (inclui 14 dígitos, etc.)
    - SEM_NUMERO         -> token vazio/inválido
    """
    if not token:
        return "SEM_NUMERO", None
    if ALPHA_RE.search(token):
        return "SEM_NUMERO", None
    if NEW_PATTERN_STRICT.match(token):
        return "PADRAO_ATUAL", token
    coerced = _coerce_to_new(token)
    if coerced:
        return "PADRAO_ATUAL", coerced
    return "PADRAO_ANTERIOR", token


def _extract(nome: str, descricao: str):
    """
    Estratégia:
    - Se nome começa com letras: procurar no FINAL (nome depois descrição).
      Se achar, aplicar. Se não, SEM_NUMERO.
    - Caso geral:
      1) início do NOME
      2) início da DESCRIÇÃO
    Retorna: (numero, classificacao, nome_sugerido, fonte, posicao, match_bruto, aplicar_auto)
    """
    nome = nome or ""
    descricao = descricao or ""

    starts_with_alpha = bool(re.match(r"^[^\d]+", nome))

    if starts_with_alpha:

        for field, text in (("nome_fim", nome), ("descricao_fim", descricao)):
            tok, a, b = _last_numericish_token(text)
            if tok:
                cls, normalized = _classify_token(tok)

                if field == "nome_fim":
                    nome_sug = re.sub(r"\s{2,}", " ", nome[:a].strip()).strip() or nome
                else:
                    nome_sug = nome

                return (normalized or tok, cls, nome_sug, field, a, tok, True)
        return None, "SEM_NUMERO", nome, None, None, None, False

    tok, a, b = _first_token(nome)
    if tok and not ALPHA_RE.search(tok):
        cls, normalized = _classify_token(tok)
        resto = (nome[b:]).lstrip(" /-_;\t")
        nome_sug = re.sub(r"\s{2,}", " ", resto).strip() or (nome or "")
        return (normalized or tok, cls, nome_sug, "nome", 0, tok, True)

    tok, a, b = _first_token(descricao)
    if tok and not ALPHA_RE.search(tok):
        cls, normalized = _classify_token(tok)
        nome_sug = nome
        return (normalized or tok, cls, nome_sug, "descricao", 0, tok, True)

    return None, "SEM_NUMERO", nome, None, None, None, False


@admin.action(description="Simular extração do Número Patrimonial → CSV")
@admin.action(
    description="Simular extração do Número Patrimonial → CSV (TODOS os bens)"
)
def simular_extracao_numero(modeladmin, request, queryset):

    qs = modeladmin.model.objects.filter(numero_patrimonial__isnull=False).iterator()

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="simulacao_135782_all.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "id",
            "nome_atual",
            "descricao_atual",
            "numero_patrimonial_atual",
            "numero_extraido",
            "classificacao",
            "fonte",
            "posicao",
            "match_bruto",
            "nome_sugerido",
            "aplicar_auto",
            "elegivel_aplicacao",
        ]
    )

    for bem in qs:
        num_atual = (bem.numero_patrimonial or "").strip()
        numero, cls, nome_sug, fonte, pos, raw, aplicar_auto = _extract(
            bem.nome, getattr(bem, "descricao", "")
        )

        elegivel = (num_atual == "") and bool(aplicar_auto)

        writer.writerow(
            [
                bem.id,
                bem.nome,
                getattr(bem, "descricao", ""),
                num_atual,
                numero or "",
                cls,
                fonte or "",
                pos if pos is not None else "",
                raw or "",
                nome_sug or "",
                "True" if aplicar_auto else "False",
                "True" if elegivel else "False",
            ]
        )

    return response


@admin.action(description="Aplicar extração do Número Patrimonial (somente sem número)")
@admin.action(
    description="(135782/V5) Aplicar extração do Número Patrimonial (somente sem número)"
)
def aplicar_extracao_numero(modeladmin, request, queryset):

    if not request.user.is_gestor_patrimonio:
        messages.error(
            request,
            "Você não tem permissão para executar esta ação. Restrito ao grupo GESTOR_PATRIMONIO.",
        )
        return None

    Model = modeladmin.model
    base_qs = queryset.filter(
        Q(numero_patrimonial__isnull=True) | Q(numero_patrimonial="")
    )

    if request.POST.get("confirm") != "yes":
        selected_ids = list(base_qs.values_list("pk", flat=True))

        existentes = set(
            Model.objects.exclude(numero_patrimonial__isnull=True)
            .exclude(numero_patrimonial="")
            .values_list("numero_patrimonial", flat=True)
        )

        propostos = {}
        numeros_todos = []
        for pk in selected_ids:
            bem = Model.objects.only(
                "id", "nome", "descricao", "numero_patrimonial"
            ).get(pk=pk)
            numero, cls, nome_sug, fonte, pos, raw, aplicar_auto = _extract(
                bem.nome, getattr(bem, "descricao", "")
            )
            if cls in ("PADRAO_ATUAL", "PADRAO_ANTERIOR") and numero:
                numeros_todos.append(numero)
            propostos[pk] = {
                "numero": numero,
                "cls": cls,
                "fonte": fonte,
                "aplicar_auto": bool(aplicar_auto),
                "nome": bem.nome,
                "num_atual": (bem.numero_patrimonial or "").strip() or "—",
            }

        contagem = Counter(numeros_todos)
        duplicados_ids = {
            pk
            for pk, info in propostos.items()
            if info["numero"]
            and (info["numero"] in existentes or contagem.get(info["numero"], 0) > 1)
        }
        amostra_ids = sorted(
            selected_ids, key=lambda _pk: (0 if _pk in duplicados_ids else 1, _pk)
        )

        sample_qs = list(Model.objects.filter(pk__in=amostra_ids))
        preview = []
        for bem in sample_qs:
            info = propostos[bem.pk]
            numero = info["numero"]
            cls = info["cls"]
            fonte = info["fonte"] or "—"
            aplicar_auto = info["aplicar_auto"]
            is_dup = bem.pk in duplicados_ids

            if is_dup and numero:
                cls_preview = "DUPLICADO"
                num_result = numero
                aplicar_preview = False
                flag_antigo = cls == "PADRAO_ANTERIOR"
                flag_sem = False
            else:
                if cls == "PADRAO_ATUAL":
                    cls_preview, num_result = "PADRAO_ATUAL", numero
                    flag_antigo, flag_sem = False, False
                    aplicar_preview = aplicar_auto
                elif cls == "PADRAO_ANTERIOR":
                    cls_preview, num_result = "PADRAO_ANTERIOR", numero
                    flag_antigo, flag_sem = True, False
                    aplicar_preview = aplicar_auto
                else:
                    cls_preview, num_result = (
                        "SEM_NUMERO",
                        "(será gerado automaticamente)",
                    )
                    flag_antigo, flag_sem = False, True
                    aplicar_preview = aplicar_auto

            preview.append(
                {
                    "id": bem.pk,
                    "nome": info["nome"],
                    "numero_atual": info["num_atual"],
                    "numero_resultado": num_result or "",
                    "classificacao": cls_preview,
                    "fonte": fonte,
                    "aplicar_auto": aplicar_preview and not is_dup,
                    "numero_formato_antigo": flag_antigo,
                    "sem_numeracao": flag_sem,
                    "duplicado": is_dup,
                }
            )
        preview = sorted(
            preview,
            key=lambda r: (
                0 if r["duplicado"] else 1,
                (
                    r["numero_resultado"].replace(".", "").replace("-", "").zfill(13)
                    if r["numero_resultado"] and r["numero_resultado"][0].isdigit()
                    else "9999999999999"
                ),
            ),
        )
        context = modeladmin.admin_site.each_context(request)
        context.update(
            {
                "title": "Confirmar aplicação IRREVERSÍVEL — Extração de Número Patrimonial",
                "total": len(selected_ids),
                "duplicados_total": len(duplicados_ids),
                "preview": preview,
                "preview_limit": 100,
                "selected_ids": selected_ids,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "opts": Model._meta,
                "objects_name": str(Model._meta.verbose_name_plural),
                "action": "aplicar_extracao_numero",
            }
        )
        return TemplateResponse(request, "admin/confirm_action.html", context)

    atualizados, erros, ignorados_duplicados = 0, 0, 0

    posted_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
    if not posted_ids:
        messages.warning(
            request, "Nenhum item foi enviado na confirmação. Ação cancelada."
        )
        return None

    existentes = set(
        Model.objects.exclude(numero_patrimonial__isnull=True)
        .exclude(numero_patrimonial="")
        .values_list("numero_patrimonial", flat=True)
    )

    objs_post = list(
        Model.objects.filter(pk__in=posted_ids).only(
            "id", "nome", "descricao", "numero_patrimonial"
        )
    )
    propostos_post = {}
    numeros_post = []
    for bem in objs_post:
        numero, cls, nome_sug, fonte, pos, raw, aplicar_auto = _extract(
            bem.nome, getattr(bem, "descricao", "")
        )
        propostos_post[bem.pk] = (numero, cls, aplicar_auto, nome_sug)
        if cls in ("PADRAO_ATUAL", "PADRAO_ANTERIOR") and numero:
            numeros_post.append(numero)

    contagem_post = Counter(numeros_post)
    dup_ids_runtime = {
        pk
        for pk, (numero, cls, _, __) in propostos_post.items()
        if numero
        and cls in ("PADRAO_ATUAL", "PADRAO_ANTERIOR")
        and (numero in existentes or contagem_post.get(numero, 0) > 1)
    }

    ids_to_process = [pk for pk in posted_ids if pk not in dup_ids_runtime]
    ignorados_duplicados = len(posted_ids) - len(ids_to_process)

    with transaction.atomic():
        qs = (
            Model.objects.filter(pk__in=ids_to_process)
            .select_for_update(skip_locked=True)
            .order_by("pk")
        )

        for bem in qs:
            with transaction.atomic():
                try:
                    numero, cls, aplicar_auto, nome_sug = propostos_post.get(
                        bem.pk, (None, "SEM_NUMERO", False, None)
                    )

                    if not aplicar_auto:
                        if cls == "SEM_NUMERO" or not numero:
                            bem.sem_numeracao = True
                            bem.full_clean()
                            bem.save(update_fields=["sem_numeracao", "atualizado_em"])
                            atualizados += 1
                        continue

                    if cls == "PADRAO_ATUAL":
                        bem.numero_patrimonial = numero
                        bem.numero_formato_antigo = False
                        bem.sem_numeracao = False
                    elif cls == "PADRAO_ANTERIOR":
                        bem.numero_patrimonial = numero
                        bem.numero_formato_antigo = True
                        bem.sem_numeracao = False
                    else:
                        bem.sem_numeracao = True

                    if nome_sug and nome_sug != bem.nome:
                        bem.nome = nome_sug

                    bem.full_clean()
                    bem.save(
                        update_fields=[
                            "numero_patrimonial",
                            "numero_formato_antigo",
                            "sem_numeracao",
                            "nome",
                            "atualizado_em",
                        ]
                    )
                    atualizados += 1

                except (ValidationError, IntegrityError):
                    transaction.set_rollback(True)
                    erros += 1
                except Exception:
                    transaction.set_rollback(True)
                    erros += 1

    messages.info(
        request,
        f"Extração aplicada. Atualizados: {atualizados}. Erros: {erros}. Ignorados (duplicados): {ignorados_duplicados}.",
    )
    return None
