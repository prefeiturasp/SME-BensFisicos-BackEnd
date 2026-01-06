# Tipos de Inventário
CONCILIACAO_ANUAL = "anual"
CONCILIACAO_EVENTUAL = "eventual"
TIPOS_CONCILIACAO = ((CONCILIACAO_ANUAL, "Anual"), (CONCILIACAO_EVENTUAL, "Eventual"))

# Status do Inventário
CONCILIACAO_EM_ABERTO = "em_aberto"
CONCILIACAO_FECHADO = "fechado"
CONCILIACAO_FECHADO_ADMIN = "fechado_admin"
STATUS_CONCILIACAO = (
    (CONCILIACAO_EM_ABERTO, "Aberta"),
    (CONCILIACAO_FECHADO, "Fechada"),
    (CONCILIACAO_FECHADO_ADMIN, "Fechado pelo Administrador - Não Conciliado")
)

# Situações de Item no Inventário
ENCONTRADO_SEM_DIVERGENCIA = "encontrado_sem_divergencia"
ENCONTRADO = "encontrado"
NAO_ENCONTRADO = "nao_encontrado"
DIVERGENTE = "divergente"
BAIXA_FISICA = "baixa_fisica"

SITUACOES_ITEM_CONCILIACAO = (
    (ENCONTRADO_SEM_DIVERGENCIA, "Encontrado sem divergência"),
    (ENCONTRADO, "Encontrado"),
    (NAO_ENCONTRADO, "Não encontrado"),
    (DIVERGENTE, "Divergente"),
    (BAIXA_FISICA, "Baixa Física"),
)
