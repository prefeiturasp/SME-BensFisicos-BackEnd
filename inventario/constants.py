# Tipos de Inventário
INVENTARIO_ANUAL = "anual"
INVENTARIO_EVENTUAL = "eventual"
TIPOS_INVENTARIO = ((INVENTARIO_ANUAL, "Anual"), (INVENTARIO_EVENTUAL, "Eventual"))

# Status do Inventário
INVENTARIO_EM_ABERTO = "em_aberto"
INVENTARIO_FECHADO = "fechado"
STATUS_INVENTARIO = (
    (INVENTARIO_EM_ABERTO, "Em aberto"),
    (INVENTARIO_FECHADO, "Fechado"),
)

# Situações de Item no Inventário
ENCONTRADO_SEM_DIVERGENCIA = "encontrado_sem_divergencia"
ENCONTRADO = "encontrado"
NAO_ENCONTRADO = "nao_encontrado"
DIVERGENTE = "divergente"
BAIXA_FISICA = "baixa_fisica"

SITUACOES_ITEM_INVENTARIO = (
    (ENCONTRADO_SEM_DIVERGENCIA, "Encontrado sem divergência"),
    (ENCONTRADO, "Encontrado"),
    (NAO_ENCONTRADO, "Não encontrado"),
    (DIVERGENTE, "Divergente"),
    (BAIXA_FISICA, "Baixa Física"),
)
