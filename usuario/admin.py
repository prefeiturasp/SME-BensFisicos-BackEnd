from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin
from usuario.models import Usuario
from django_admin_listfilter_dropdown.filters import DropdownFilter, RelatedDropdownFilter, ChoiceDropdownFilter
from rangefilter.filters import DateRangeFilter, DateTimeRangeFilter, NumericRangeFilter


class CustomUserModelAdmin(UserAdmin):
    model = Usuario
    list_display = ('id', 'nome', 'email', 'unidade_administrativa', 'date_joined', )
    search_fields = ('nome', )
    search_help_text = 'Pesquise por nome.'

    list_filter = UserAdmin.list_filter + (
        ('unidade_administrativa__sigla', DropdownFilter),
        ('date_joined', DateRangeFilter),
    )
    fieldsets = (('Acesso', {'fields': ('username', 'password')}), ('Informações pessoais', {'fields': ('nome', 'email', 'unidade_administrativa', )}),
                 ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', )}), ('Datas importantes', {'fields': ('last_login', 'date_joined')}))
    add_fieldsets = fieldsets


admin.site.unregister(Group)
admin.site.register(Usuario, CustomUserModelAdmin)