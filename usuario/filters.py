import django_filters
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()


class UsuarioFilter(django_filters.FilterSet):

    # membro da equipe
    is_staff = django_filters.BooleanFilter()

    # superusuário
    is_superuser = django_filters.BooleanFilter()

    # ativo (usado para soft delete)
    is_active = django_filters.BooleanFilter()

    # grupo
    groups = django_filters.ModelChoiceFilter(
        field_name="groups__id",
        queryset=Group.objects.all()
    )

    # sigla do grupo (ex: ST-UA)
    group_name = django_filters.CharFilter(
        field_name="groups__name",
        lookup_expr="icontains"
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
            "groups",
            "group_name",
        ]
