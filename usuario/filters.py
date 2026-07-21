import django_filters
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class UsuarioFilter(django_filters.FilterSet):

    # membro da equipe
    is_staff = django_filters.BooleanFilter()

    # superusuário
    is_superuser = django_filters.BooleanFilter()

    # ativo (usado para soft delete)
    is_active = django_filters.BooleanFilter()

    # sigla do grupo (ex: Gestor Patrimonio)
    group_name = django_filters.CharFilter(
        field_name="groups__name",
        lookup_expr="icontains"
    )

    unidade = django_filters.CharFilter(
        method="filter_unidade"
    )

    unidade_orcamentaria = django_filters.NumberFilter(
        field_name="unidade_orcamentaria_id"
    )

    # data inicial
    date_joined_after = django_filters.DateFilter(
        field_name="date_joined",
        lookup_expr="gte"
    )

    # data final
    date_joined_before = django_filters.DateFilter(
        field_name="date_joined",
        lookup_expr="lte"
    )

    class Meta:
        model = User
        fields = [
            "is_staff",
            "is_superuser",
            "is_active",
            "group_name",
            "unidade",
            "unidade_orcamentaria",
        ]

    def filter_unidade(self, queryset, name, value):
        return queryset.filter(
            Q(unidade_administrativa__nome__icontains=value) |
            Q(unidade_administrativa__codigo__icontains=value) |
            Q(unidade_administrativa__sigla__icontains=value)
        )
