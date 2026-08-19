"""
(POST /api/bens/importar/).

Estende BemPatrimonialResource (o resource compartilhado com o Django Admin)
para aplicar a regra de negócio de aprovação diferenciada por perfil, sem
alterar em nada o comportamento da importação via Django Admin — que continua
usando o BemPatrimonialResource original, no qual todo bem importado entra
com status Aguardando Aprovação.

Regra aplicada aqui (somente na API):
- Gestor de Patrimônio (ou superusuário): os bens importados já entram
  APROVADO, sendo incorporados imediatamente à listagem da Unidade
  Administrativa, dispensando a etapa de aprovação. Para cada bem é
  registrado o histórico de aprovação (StatusBemPatrimonial), replicando a
  auditoria da ação "Aprovar bens".
- Operador de Inventário (e qualquer outro perfil): mantém o fluxo atual,
  entrando com status Aguardando Aprovação até que um Gestor aprove.

Todas as demais validações (estrutura da planilha, duplicidade, tudo-ou-nada,
normalizações de marca/modelo/valor, UA do usuário) são herdadas sem
modificação de BemPatrimonialResource.

Unidade Administrativa de destino:
- Quando o usuário está logado numa UA (request.user.unidade_administrativa
  preenchida), os bens são gravados nessa UA — comportamento herdado.
- Quando o usuário está logado numa UO (sem UA direta), o front envia a UA
  escolhida; a view valida que ela pertence ao escopo do usuário e a repassa
  a este resource via `unidade_administrativa`, que passa a ser usada na
  gravação dos bens.
"""

from bem_patrimonial import constants
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialResource
from bem_patrimonial.models import StatusBemPatrimonial


class BemPatrimonialAPIResource(BemPatrimonialResource):
    """Resource de importação da API, com aprovação condicionada ao perfil."""

    def __init__(self, *args, unidade_administrativa=None, **kwargs):
        """
        unidade_administrativa: UA de destino explícita (opcional). Quando
        informada (usuário logado em UO que escolheu a UA no front), sobrepõe a
        UA do usuário na gravação dos bens. Quando None, mantém o comportamento
        herdado (usa request.user.unidade_administrativa).
        """
        super().__init__(*args, **kwargs)
        self.unidade_administrativa = unidade_administrativa

    def _usuario_aprova_na_importacao(self) -> bool:
        """
        Indica se o usuário autenticado tem seus bens incorporados
        imediatamente (APROVADO) na importação, dispensando aprovação.

        Segue a mesma precedência de perfil adotada no restante do sistema
        (ex.: action aprovar_bens, serializers): Gestor de Patrimônio — e o
        superusuário — aprovam direto; Operador de Inventário (ou qualquer
        outro perfil) permanece no fluxo de Aguardando Aprovação.
        """
        user = getattr(self, "request", None) and self.request.user
        if not user:
            return False
        return bool(
            getattr(user, "is_gestor_patrimonio", False)
            or getattr(user, "is_superuser", False)
        )

    def _status_inicial_para_importacao(self) -> str:
        """Status com que cada bem importado deve ser persistido."""
        if self._usuario_aprova_na_importacao():
            return constants.APROVADO
        return constants.AGUARDANDO_APROVACAO

    def _ua_para_importacao(self):
        """
        UA de destino: a explícita (escolhida pelo usuário logado em UO), quando
        informada; caso contrário, a UA do usuário autenticado (comportamento
        herdado). Usada tanto na validação (before_import) quanto na gravação.
        """
        if self.unidade_administrativa is not None:
            return self.unidade_administrativa
        return super()._ua_para_importacao()

    def before_save_instance(self, instance, *args, **kwargs):
        """
        Reaproveita toda a preparação da instância feita pela superclasse
        (limpeza de PK, criado_por, UA de destino, número patrimonial) e apenas
        ajusta o status inicial conforme o perfil de quem importa.
        """
        super().before_save_instance(instance, *args, **kwargs)
        # A superclasse define AGUARDANDO_APROVACAO; sobrescrevemos conforme o
        # perfil apenas no fluxo da API.
        instance.status = self._status_inicial_para_importacao()

    def after_save_instance(self, instance, *args, **kwargs):
        """
        Registra o histórico de status do bem recém-importado quando ele entra
        já APROVADO (importação por Gestor/superusuário).

        O signal `cria_primeiro_status_bem_patrimonial` só cria histórico para
        bens Aguardando Aprovação, então aqui criamos explicitamente o
        StatusBemPatrimonial de APROVADO — mesma auditoria da action
        "Aprovar bens", garantindo rastreabilidade de quem incorporou o bem.

        Para bens Aguardando Aprovação nada é feito aqui: o histórico inicial
        já é criado pelo signal de post_save do BemPatrimonial.

        Não faz nada em dry_run (nunca usado pela API, mas mantido por
        segurança) nem quando o status não é APROVADO.
        """
        super().after_save_instance(instance, *args, **kwargs)

        # Assinatura em django-import-export 3.0.2:
        # after_save_instance(self, instance, using_transactions, dry_run).
        # Lemos os parâmetros de forma defensiva para não acoplar à posição.
        dry_run = kwargs.get("dry_run")
        if dry_run is None and len(args) >= 2:
            dry_run = args[1]
        if dry_run:
            return

        if instance.status != constants.APROVADO:
            return

        usuario = getattr(self, "request", None) and self.request.user
        StatusBemPatrimonial.objects.create(
            bem_patrimonial=instance,
            status=constants.APROVADO,
            atualizado_por=usuario,
            observacao="Aprovado automaticamente na importação (Gestor de Patrimônio)",
        )
