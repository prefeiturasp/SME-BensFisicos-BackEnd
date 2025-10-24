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
        "nome",
        "unidade_administrativa",
        "status",
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

    def get_list_display(self, request):
        if request.user.is_operador_inventario:
            return ("numero_patrimonial", "nome", "status")
        return ("numero_patrimonial", "nome", "unidade_administrativa", "status")

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

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if obj is None:  # Só valida na criação
            original_clean = form.clean

            def custom_clean(form_self):
                cleaned_data = original_clean(form_self)

                if (
                    request.user.unidade_administrativa
                    and not request.user.unidade_administrativa.is_ativa
                ):
                    raise ValidationError(
                        f"Não é possível criar bens patrimoniais. Sua unidade administrativa "
                        f"'{request.user.unidade_administrativa.nome}' está inativa. "
                        "Entre em contato com o gestor de patrimônio."
                    )

                return cleaned_data

            form.clean = custom_clean

        return form

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.criado_por = request.user
        try:
            super().save_model(request, obj, form, change)
        else:
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

        f_num = form.base_fields.get("numero_patrimonial")
        f_ant = form.base_fields.get("numero_formato_antigo")
        f_sem = form.base_fields.get("sem_numeracao")

        if has_instance:
            if f_ant:
                f_ant.disabled = True
                f_ant.widget.attrs["disabled"] = "disabled"
                f_ant.widget.attrs["title"] = "Imutável após a criação."
            if f_sem:
                f_sem.disabled = True
                f_sem.widget.attrs["disabled"] = "disabled"
                f_sem.widget.attrs["title"] = "Imutável após a criação."
        else:
            if f_ant:
                if sem_flag:
                    f_ant.widget.attrs["disabled"] = "disabled"
                    f_ant.widget.attrs["title"] = (
                        "Desabilitado quando 'Sem numeração' está ativo."
                    )
                else:
                    f_ant.widget.attrs.pop("disabled", None)
                    f_ant.widget.attrs.pop("title", None)
            if f_sem:
                if antigo_flag:
                    f_sem.widget.attrs["disabled"] = "disabled"
                    f_sem.widget.attrs["title"] = (
                        "Desabilitado quando 'Formato antigo' está ativo."
                    )
                else:
                    f_sem.widget.attrs.pop("disabled", None)
                    f_sem.widget.attrs.pop("title", None)

        if f_num:
            f_num.widget.attrs["autocomplete"] = "off"
            f_num.widget.attrs["data-has-instance"] = "1" if has_instance else "0"
            if not has_instance and sem_flag:
                f_num.widget.attrs["placeholder"] = "Gerado automaticamente"
                f_num.widget.attrs["readonly"] = "readonly"
            else:
                f_num.widget.attrs.pop("readonly", None)
                if not antigo_flag and not sem_flag:
                    f_num.widget.attrs["placeholder"] = "000.000000000-0"
                    f_num.widget.attrs["pattern"] = r"^\d{3}\.\d{9}-\d$"
                else:
                    f_num.widget.attrs.pop("pattern", None)

            if has_instance and getattr(obj, "sem_numeracao", False):
                f_num.disabled = True
                f_num.widget.attrs["disabled"] = "disabled"

        return form

    def render_change_form(self, request, context, *args, **kwargs):
        response = super().render_change_form(request, context, *args, **kwargs)
        script = r"""
            <script>
                (function(){
                function id(el){ return document.getElementById(el); }
                function onlyDigits(s){ return (s||'').replace(/\D/g,''); }
                function formatNPatFromDigits(d){
                    d = (d||'').slice(0,13);
                    var p1=d.slice(0,3), p2=d.slice(3,12), p3=d.slice(12,13);
                    if (d.length <= 3) return p1;
                    if (d.length <= 12) return p1 + '.' + p2;
                    return p1 + '.' + p2 + '-' + p3;
                }

                function markServerState(elem){
                    if(!elem) return;
                    
                    elem.dataset.serverDisabled = elem.disabled ? "1" : "0";
                    
                    elem.removeAttribute('data-client-disabled');
                }

                function clientDisable(elem, reasonAttr){
                    if(!elem) return;
                    if(elem.disabled) return; 
                    elem.setAttribute('disabled','disabled');
                    
                    elem.setAttribute('data-client-disabled','1');
                    if(reasonAttr) elem.setAttribute(reasonAttr,'1');
                }

                function clientEnable(elem, reasonAttr){
                    if(!elem) return;
                    
                    if(elem.dataset && elem.dataset.serverDisabled === "1"){
                    
                    
                    elem.removeAttribute('data-client-disabled');
                    if(reasonAttr) elem.removeAttribute(reasonAttr);
                    return;
                    }
                    
                    elem.removeAttribute('disabled');
                    elem.removeAttribute('data-client-disabled');
                    if(reasonAttr) elem.removeAttribute(reasonAttr);
                }

                function applyState(){
                    var chkSem = id('id_sem_numeracao');
                    var chkAnt = id('id_numero_formato_antigo');
                    var input  = id('id_numero_patrimonial');
                    if (!input) return;

                    
                    var semServer = chkSem && chkSem.dataset && chkSem.dataset.serverDisabled === "1";
                    var antServer = chkAnt && chkAnt.dataset && chkAnt.dataset.serverDisabled === "1";

                    
                    if (chkSem && chkSem.checked && !semServer){
                    
                    if (chkAnt){
                        chkAnt.checked = false;
                        clientDisable(chkAnt, 'data-disabled-because-sem');
                    }
                    
                    input.value = '';
                    input.setAttribute('readonly','readonly');
                    input.setAttribute('placeholder','Gerado automaticamente');
                    input.removeAttribute('pattern');
                    return;
                    }

                    
                    if (chkSem && !chkSem.checked){
                    if (chkAnt){
                        
                        clientEnable(chkAnt, 'data-disabled-because-sem');
                    }
                    
                    input.removeAttribute('readonly');
                    input.removeAttribute('placeholder');
                    }

                    
                    if (chkAnt && chkAnt.checked && !antServer){
                    
                    if (chkSem){
                        chkSem.checked = false;
                        clientDisable(chkSem, 'data-disabled-because-antigo');
                    }
                    
                    input.removeAttribute('pattern');
                    input.removeAttribute('readonly');
                    input.setAttribute('placeholder','Valor livre (formato antigo)');
                    return;
                    }

                    
                    if (chkAnt && !chkAnt.checked){
                    if (chkSem){
                        clientEnable(chkSem, 'data-disabled-because-antigo');
                    }
                    
                    input.removeAttribute('readonly');
                    }

                    
                    input.removeAttribute('readonly');
                    if (! (chkAnt && chkAnt.checked) && !(chkSem && chkSem.checked) ){
                    input.setAttribute('pattern','^\\d{3}\\.\\d{9}-\\d$');
                    input.value = formatNPatFromDigits(onlyDigits(input.value));
                    input.setAttribute('placeholder','000.000000000-0');
                    } else {
                    input.removeAttribute('pattern');
                    }
                }

                function bind(){
                    var chkSem = id('id_sem_numeracao');
                    var chkAnt = id('id_numero_formato_antigo');
                    var input  = id('id_numero_patrimonial');

                    
                    markServerState(chkSem);
                    markServerState(chkAnt);

                    
                    if (chkSem && chkSem.dataset.serverDisabled !== "1"){
                    chkSem.addEventListener('change', applyState);
                    }
                    if (chkAnt && chkAnt.dataset.serverDisabled !== "1"){
                    chkAnt.addEventListener('change', applyState);
                    }

                    if (input){
                    input.addEventListener('input', function(){
                        
                        if (!(chkSem && chkSem.checked) && !(chkAnt && chkAnt.checked)){
                        input.value = formatNPatFromDigits(onlyDigits(input.value));
                        }
                    });
                    }

                    
                    applyState();
                }

                document.addEventListener('DOMContentLoaded', bind);
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
