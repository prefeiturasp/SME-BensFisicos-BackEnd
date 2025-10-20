from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import Q, OuterRef, Subquery
from bem_patrimonial.models import (
    BemPatrimonial,
    StatusBemPatrimonial,
    UnidadeAdministrativaBemPatrimonial,
)
from bem_patrimonial.formats import PDFFormat
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from rangefilter.filters import DateRangeFilter
from import_export.formats.base_formats import CSV, XLS, XLSX, HTML


class UnidadeAdministrativaBemPatrimonialInline(admin.TabularInline):
    model = UnidadeAdministrativaBemPatrimonial
    extra = 0


class StatusBemPatrimonialInline(admin.TabularInline):
    model = StatusBemPatrimonial
    extra = 0
    readonly_fields = (
        "atualizado_por",
        "atualizado_em",
    )


class BemPatrimonialResource(resources.ModelResource):
    quantidade_unidade = fields.Field(
        column_name="quantidade",
        attribute="quantidade_unidade",
    )

    class Meta:
        model = BemPatrimonial
        fields = (
            "id",
            "status",
            "nome",
            "data_compra_entrega",
            "origem",
            "marca",
            "modelo",
            "descricao",
            "quantidade_unidade",
            "valor_unitario",
            "numero_processo",
            "autorizacao_no_doc_em",
            "numero_nibpm",
            "numero_cimbpm",
            "numero_patrimonial",
            "localizacao",
            "numero_serie",
            "criado_por__nome",
            "criado_em",
        )
        export_order = fields


class BemPatrimonialAdmin(ImportExportModelAdmin):
    model = BemPatrimonial
    list_display = (
        "numero_patrimonial",
        "status",
        "descricao",
        "criado_por",
        "criado_em",
    )
    search_fields = (
        "numero_patrimonial",
        "nome",
        "descricao",
        "marca",
        "modelo",
        "localizacao",
        "numero_processo",
    )
    search_help_text = "Pesquise por número patrimonial, nome, descrição, marca, modelo, localização ou número de processo."
    resource_class = BemPatrimonialResource

    list_filter = (
        "status",
        "sem_numeracao",
        "numero_formato_antigo",
        ("criado_em", DateRangeFilter),
    )

    readonly_fields = (
        "status",
        "criado_por",
        "criado_em",
    )

    fields = (
        "status",
        ("numero_patrimonial", "numero_formato_antigo", "sem_numeracao"),
        "nome",
        "descricao",
        ("quantidade", "valor_unitario"),
        ("marca", "modelo"),
        ("data_compra_entrega"),
        ("origem", "numero_processo"),
        "autorizacao_no_doc_em",
        ("numero_nibpm", "numero_cimbpm"),
        "localizacao",
        "numero_serie",
    )

    inlines = [StatusBemPatrimonialInline, UnidadeAdministrativaBemPatrimonialInline]

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.criado_por = request.user
        try:
            super().save_model(request, obj, form, change)
        except IntegrityError as e:
            if "numero_patrimonial" in str(e).lower():
                form.add_error(
                    "numero_patrimonial",
                    "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema.",
                )
                raise ValidationError(
                    {
                        "numero_patrimonial": "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema."
                    }
                )
            raise

    def get_queryset(self, request):
        queryset = BemPatrimonial.objects.all()
        if request.user.is_operador_inventario:
            return queryset.filter(
                Q(unidadeadministrativabempatrimonial__quantidade__gt=0)
                & Q(
                    unidadeadministrativabempatrimonial__unidade_administrativa=request.user.unidade_administrativa
                )
            ).distinct("id")
        return queryset

    def get_export_queryset(self, request):
        queryset = super().get_export_queryset(request)

        if request.user.is_operador_inventario:
            queryset = (
                queryset.filter(
                    Q(unidadeadministrativabempatrimonial__quantidade__gt=0)
                    & Q(
                        unidadeadministrativabempatrimonial__unidade_administrativa=request.user.unidade_administrativa
                    )
                )
                .distinct("id")
                .annotate(
                    quantidade_unidade=Subquery(
                        UnidadeAdministrativaBemPatrimonial.objects.filter(
                            bem_patrimonial=OuterRef("id"),
                            unidade_administrativa=request.user.unidade_administrativa,
                        ).values("quantidade")[:1],
                        output_field=models.IntegerField(),
                    )
                )
            )

        return queryset

    def get_export_formats(self):
        return [CSV, XLSX, XLS, HTML, PDFFormat]

    def get_resource_kwargs(self, request, **kwargs):
        rk = super().get_resource_kwargs(request, **kwargs)
        rk["request"] = request
        return rk

    def get_export_data(self, file_format, queryset, *args, **kwargs):
        if isinstance(file_format, PDFFormat):
            request = kwargs.get("request")
            file_format._export_request = request
            file_format._export_queryset = queryset

        return super().get_export_data(file_format, queryset, *args, **kwargs)

    def save_formset(self, request, form, formset, change):
        if formset.model is StatusBemPatrimonial:
            self.save_status(request, form, formset, change)
        formset.save()

    def save_status(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        for instance in instances:
            instance.atualizado_por = request.user
            instance.save()

        formset.save_m2m()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        has_instance = bool(getattr(obj, "pk", None))

        # Flags atuais (GET usa obj, POST usa request)
        if request.method == "POST":
            sem_flag = request.POST.get("sem_numeracao") in ("on", "true", "1")
            antigo_flag = request.POST.get("numero_formato_antigo") in (
                "on",
                "true",
                "1",
            )
        else:
            sem_flag = bool(getattr(obj, "sem_numeracao", False))
            antigo_flag = bool(getattr(obj, "numero_formato_antigo", False))

        # ---- Regra 1: na EDIÇÃO, travar "formato antigo" e "sem numeração"
        f_ant = form.base_fields.get("numero_formato_antigo")
        if f_ant:
            if has_instance:
                f_ant.disabled = True  # não editável e valor preservado
                f_ant.widget.attrs["title"] = "Imutável após a criação."
            else:
                f_ant.disabled = False
                f_ant.widget.attrs.pop("title", None)

        f_sem = form.base_fields.get("sem_numeracao")
        if f_sem:
            if has_instance:
                f_sem.disabled = True  # não editável e valor preservado
                f_sem.widget.attrs["title"] = "Imutável após a criação."
            else:
                f_sem.disabled = False
                f_sem.widget.attrs.pop("title", None)

        # ---- Campo Número Patrimonial (máscara/pattern/readonly)
        f_num = form.base_fields.get("numero_patrimonial")
        if f_num:
            f_num.widget.attrs["data-mask-npat"] = "1"
            f_num.widget.attrs["autocomplete"] = "off"
            f_num.widget.attrs["data-has-instance"] = "1" if has_instance else "0"

            if has_instance:
                # Regra 2: só pode editar se NA CRIAÇÃO não foi 'sem_numeracao'
                if sem_flag:  # criado com sem_numeracao=True -> não editar
                    f_num.disabled = True  # trava totalmente (Django mantém o valor)
                    f_num.widget.attrs.pop("pattern", None)
                    # mantém o valor visível, sem placeholder
                else:
                    f_num.disabled = False  # editável
                    if antigo_flag:
                        # formato antigo -> sem pattern/máscara
                        f_num.widget.attrs["placeholder"] = (
                            "Valor livre (formato antigo)"
                        )
                        f_num.widget.attrs.pop("pattern", None)
                    else:
                        # formato novo -> pattern/máscara
                        f_num.widget.attrs["placeholder"] = "000.000000000-0"
                        f_num.widget.attrs["pattern"] = r"^\d{3}\.\d{9}-\d$"
            else:
                # CRIAÇÃO: segue a regra normal (pode marcar flags e a máscara reage)
                f_num.disabled = False
                if sem_flag:
                    # criação + sem numeração marcado -> número será gerado no save()
                    f_num.widget.attrs["placeholder"] = "Gerado automaticamente"
                    f_num.widget.attrs.pop("pattern", None)
                elif antigo_flag:
                    f_num.widget.attrs["placeholder"] = "Valor livre (formato antigo)"
                    f_num.widget.attrs.pop("pattern", None)
                else:
                    f_num.widget.attrs["placeholder"] = "000.000000000-0"
                    f_num.widget.attrs["pattern"] = r"^\d{3}\.\d{9}-\d$"

        return form

    def render_change_form(self, request, context, *args, **kwargs):
        response = super().render_change_form(request, context, *args, **kwargs)
        script = r"""
            <script>
            (function(){
            function onlyDigits(s){ return (s||'').replace(/\D/g,''); }
            function formatNPatFromDigits(d){
                d = (d||'').slice(0,13); // 3 + 9 + 1
                var p1=d.slice(0,3), p2=d.slice(3,12), p3=d.slice(12,13);
                if (d.length <= 3) return p1;
                if (d.length <= 12) return p1 + '.' + p2;
                return p1 + '.' + p2 + '-' + p3;
            }
            function shouldMask(){
                var chkAnt = document.getElementById('id_numero_formato_antigo');
                var chkSem = document.getElementById('id_sem_numeracao');
                // máscara somente quando NÃO for antigo e NÃO for sem numeração
                return !(chkAnt && chkAnt.checked) && !(chkSem && chkSem.checked);
            }
            function onInputMask(){
                var input = document.getElementById('id_numero_patrimonial');
                if (!input) return;
                // se o campo estiver desabilitado pelo admin (edit + sem_numeracao), não mascara
                if (input.disabled) return;
                if (shouldMask()){
                input.value = formatNPatFromDigits(onlyDigits(input.value));
                }
            }
            function init(){
                var input  = document.getElementById('id_numero_patrimonial');
                var chkAnt = document.getElementById('id_numero_formato_antigo');
                var chkSem = document.getElementById('id_sem_numeracao');
                if (input){
                input.addEventListener('input', onInputMask);
                input.addEventListener('blur', onInputMask);
                }
                // em "Add", os checkboxes estão habilitados -> reprocessa máscara ao mudar
                if (chkAnt && !chkAnt.disabled) chkAnt.addEventListener('change', onInputMask);
                if (chkSem && !chkSem.disabled) chkSem.addEventListener('change', onInputMask);

                // primeira aplicação
                onInputMask();
            }
            document.addEventListener('DOMContentLoaded', init);
            })();
            </script>
            """
        try:
            response.content = response.rendered_content.replace(
                "</form>", "</form>" + script
            ).encode(response.charset)
        except Exception:
            pass
        return response
