# origem bem patrimonial

REPASSE = "repasse_de_verba"
AQUISICAO = "aquisicao_direta"
TRANSFERENCIA = "transferencia"
MOVIMENTACAO = "movimentacao"

ORIGENS = (
    (REPASSE, "Repasse de verba"),
    (AQUISICAO, "Aquisição direta"),
    (TRANSFERENCIA, "Transferência"),
    (MOVIMENTACAO, "Movimentação"),
)

# status bem patrimonial

AGUARDANDO_APROVACAO = "aguardando_aprovacao"
APROVADO = "aprovado"
NAO_APROVADO = "nao_aprovado"
BLOQUEADO = "bloqueado"
BAIXA_FISICA_AGUARDANDO_APROVACAO = "baixa_fisica_aguardando_aprovacao"
BAIXA_FISICA = "baixa_fisica"
TRANSFERIDO = "transferido"

STATUS = (
    (AGUARDANDO_APROVACAO, "Aguardando aprovação"),
    (APROVADO, "Aprovado"),
    (NAO_APROVADO, "Não aprovado"),
    (BLOQUEADO, "Bloqueado para movimentação"),
    (BAIXA_FISICA_AGUARDANDO_APROVACAO, "Baixa Física - Aguardando aprovação"),
    (BAIXA_FISICA, "Baixa Física"),
    (TRANSFERIDO, "Transferido"),
)

STATUS_FINAIS_BEM = (
    BAIXA_FISICA,
    TRANSFERIDO,
)
# status movimentacao

ENVIADA = "enviada"
ACEITA = "aceita"
REJEITADA = "rejeitada"
CANCELADA = "cancelada"
AGUARDANDO_ENVIO = "aguardando_envio"
SOLICITADA = "solicitada"
RECUSADA = "recusada"

STATUS_MOVIMENTACAO = (
    (ENVIADA, "Enviada"),
    (ACEITA, "Aceita"),
    (REJEITADA, "Rejeitada"),
    (CANCELADA, "Cancelada"),
)

STATUS_BAIXA_FISICA = (
    (AGUARDANDO_ENVIO, "Aguardando envio"),
    (SOLICITADA, "Solicitada"),
    (ACEITA, "Aceita"),
    (RECUSADA, "Recusada"),
)
