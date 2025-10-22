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

STATUS = (
    (AGUARDANDO_APROVACAO, "Aguardando aprovação"),
    (APROVADO, "Aprovado"),
    (NAO_APROVADO, "Não aprovado"),
    (BLOQUEADO, "Bloqueado para movimentação"),
)
# status movimentacao

ENVIADA = "enviada"
ACEITA = "aceita"
REJEITADA = "rejeitada"

STATUS_MOVIMENTACAO = (
    (ENVIADA, "Enviada"),
    (ACEITA, "Aceita"),
    (REJEITADA, "Rejeitada"),
)
