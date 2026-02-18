from dados_comuns.models import UnidadeAdministrativa
from django.db.models import Q


def usuario_e_super_admin(usuario):
    return bool(getattr(usuario, "is_superuser", False))


def obter_unidade_orcamentaria_id_do_usuario(usuario):
    """
    Retorna o ID da UO do usuário:
    - se tiver unidade_orcamentaria_id direto, usa
    - senão, tenta derivar via unidade_administrativa.unidade_orcamentaria_id
    """
    uo_id = getattr(usuario, "unidade_orcamentaria_id", None)
    if uo_id:
        return uo_id

    ua = getattr(usuario, "unidade_administrativa", None)
    if ua:
        return getattr(ua, "unidade_orcamentaria_id", None)

    return None


def resolver_ids_escopo(usuario):
    """
    Centraliza leitura de flags e IDs usados nas regras.
    Retorna (is_super, is_gestor, ua_id, uo_id)
    """
    is_super = usuario_e_super_admin(usuario)
    is_gestor = bool(getattr(usuario, "is_gestor_patrimonio", False))
    ua_id = getattr(usuario, "unidade_administrativa_id", None)
    uo_id = obter_unidade_orcamentaria_id_do_usuario(usuario)

    return is_super, is_gestor, ua_id, uo_id


def filtrar_queryset_por_escopo(usuario, queryset, campo_ua="unidade_administrativa"):
    """
    Ordem das regras:
    1) Se tem UA associada -> filtra pela UA
    2) Se não tem UA -> verifica:
        2.1) Super admin e Gestor -> retorna UAs da UO dele (via relação em campo_ua)
        2.2) Outros -> vazio
    """
    is_super, is_gestor, ua_id, uo_id = resolver_ids_escopo(usuario)

    # 1) UA vence sempre
    if ua_id:
        return queryset.filter(**{f"{campo_ua}_id": ua_id})

    # 2.1) gestor sem UA -> restringe pela UO dele
    if is_gestor and uo_id:
        return queryset.filter(**{f"{campo_ua}__unidade_orcamentaria_id": uo_id})

    # 2.2) demais -> vazio
    return queryset.none()


def validar_objeto_no_escopo(usuario, objeto, campo_ua="unidade_administrativa"):
    """
    Mesma lógica do filtro, mas para validar um objeto específico.
    """
    is_super, is_gestor, ua_id, uo_id = resolver_ids_escopo(usuario)

    # 1) UA vence sempre
    if ua_id:
        ua_obj = getattr(objeto, campo_ua, None)
        return bool(ua_obj and getattr(ua_obj, "id", None) == ua_id)

    # 2.2) gestor sem UA -> objeto deve pertencer à UO dele
    if is_gestor and uo_id:
        ua_obj = getattr(objeto, campo_ua, None)
        return bool(
            ua_obj and getattr(ua_obj, "unidade_orcamentaria_id", None) == uo_id
        )

    return False


def filtrar_ua_origem_por_escopo(usuario, queryset_ua=None):
    """
    UAs possíveis para ORIGEM na movimentação:
    - se usuário tem UA: só ela
    - se não tem UA:
        - super admin e gestor: UAs da UO dele
        - outros: vazio
    """
    if queryset_ua is None:
        queryset_ua = UnidadeAdministrativa.objects.all()

    is_super, is_gestor, ua_id, uo_id = resolver_ids_escopo(usuario)

    if ua_id:
        return queryset_ua.filter(id=ua_id)

    if is_gestor and uo_id:
        return queryset_ua.filter(unidade_orcamentaria_id=uo_id)

    return queryset_ua.none()


def filtrar_ua_destino_por_uo_do_usuario(usuario, queryset_ua=None):
    """
    UAs possíveis para DESTINO na movimentação:
    - super admin: todas
    - demais: UAs da UO do usuário (independente do perfil)
    - sem UO: vazio
    """
    if queryset_ua is None:
        queryset_ua = UnidadeAdministrativa.objects.all()

    is_super, _is_gestor, _ua_id, uo_id = resolver_ids_escopo(usuario)

    if not uo_id:
        return queryset_ua.none()

    return queryset_ua.filter(unidade_orcamentaria_id=uo_id)


def filtrar_queryset_movimentacao_por_escopo(usuario, queryset):
    """
    Movimentações visíveis:
    - Se usuário tem UA: vê movs onde (origem=UA) OU (destino=UA)
    - Se não tem UA:
        - super admin e gestor: vê movs onde origem OU destino pertencem à UO dele
        - demais: vazio
    """
    ua_ids = list(filtrar_ua_origem_por_escopo(usuario).values_list("id", flat=True))
    if ua_ids:
        return queryset.filter(
            Q(unidade_administrativa_origem_id__in=ua_ids)
            | Q(unidade_administrativa_destino_id__in=ua_ids)
        )

    ua_uo_ids = list(
        filtrar_ua_destino_por_uo_do_usuario(usuario).values_list("id", flat=True)
    )
    if ua_uo_ids:
        return queryset.filter(
            Q(unidade_administrativa_origem_id__in=ua_uo_ids)
            | Q(unidade_administrativa_destino_id__in=ua_uo_ids)
        )

    return queryset.none()
