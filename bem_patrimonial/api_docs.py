from textwrap import dedent


# ==========================================
# DOCUMENTAÇÃO PARA A API "baixas-fisicas"
# ==========================================

# API: /api/baixas-fisicas/ (GET)
LIST_BAIXAS_FISICAS_DOC = dedent("""
Retorna uma lista paginada de baixas físicas cadastradas no sistema.

### Filtros disponíveis

- **status** → filtra por status específico (aguardando_envio, solicitada, aceita, recusada)
- **status__in** → filtra por múltiplos status (ex: aceita,solicitada)
- **unidade_administrativa_origem** → filtra por unidade administrativa de origem
- **data_aprovacao__gte** → baixas aprovadas após uma data
- **data_aprovacao__lte** → baixas aprovadas antes de uma data
- **data_criacao__gte** → baixas criadas após uma data
- **data_criacao__lte** → baixas criadas antes de uma data
- **search** → busca por número de processo, NBBPM, nome da UA, ou número/nome do bem

### Ordenação disponível

- **id** → por ID
- **data_criacao** → por data de criação
- **data_aprovacao** → por data de aprovação
- **status** → por status
- **numero_nbbpm** → por número NBBPM

Use `-` antes do campo para ordem decrescente (ex: `-data_criacao`).

A resposta segue o padrão de paginação da API.

**Importante:** O usuário visualiza apenas as baixas das unidades administrativas
às quais tem acesso (filtro de escopo aplicado automaticamente).
""")

# API: /api/baixas-fisicas/ (POST)
CREATE_BAIXAS_FISICAS_DOC = dedent("""
Cria uma nova baixa física de bens patrimoniais.

Após a criação:

- o **status** é automaticamente definido como **aguardando_envio**
- o **criado_por** recebe o usuário autenticado
- os **bens** incluídos têm seu status alterado para **baixa_fisica_aguardando_aprovacao**

### Validações aplicadas

- É obrigatório informar **ao menos um bem** para a baixa
- A **data de baixa** não pode ser futura
- A **unidade administrativa de origem** deve estar ativa
- Bens não podem estar em outra baixa física pendente

Somente usuários **Gestor de Patrimônio** ou **Operador de Inventário** podem executar esta operação.
""")

# API: /api/baixas-fisicas/{id}/ (GET)
RETRIEVE_BAIXAS_FISICAS_DOC = dedent("""
Retorna todas as informações de uma baixa física específica.

A baixa é identificada pelo **ID** informado na URL.

A resposta inclui:

- Dados completos da baixa
- Lista de todos os **itens (bens)** associados
- **URLs de ações** disponíveis conforme o status atual:
  - `url_enviar_solicitacao` → se status for aguardando_envio
  - `url_aprovar` → se status for solicitada
  - `url_cancelar` → se status for aguardando_envio ou solicitada
  - `url_gerar_nbbpm` → se status for aceita e tiver número NBBPM
""")

# API: /api/baixas-fisicas/{id}/ (PUT/PATCH)
UPDATE_BAIXAS_FISICAS_DOC = dedent("""
Atualiza os dados de uma baixa física existente.

### Restrições importantes

- Somente baixas com status **aguardando_envio** podem ser editadas
- Não é possível alterar a **unidade administrativa de origem**

### Gerenciamento de itens

Ao atualizar a lista de itens:

- **Itens com ID** → são atualizados
- **Itens sem ID** → são criados
- **Itens não enviados** → são removidos

O status dos bens é ajustado automaticamente conforme inclusão/remoção de itens.

Todas as alterações são aplicadas de forma transacional (tudo ou nada).
""")

# API: /api/baixas-fisicas/{id}/enviar-solicitacao/ (POST)
ENVIAR_SOLICITACAO_DOC = dedent("""
Envia a baixa física para aprovação do Gestor de Patrimônio.

### Comportamento

1. Valida que o status é **aguardando_envio**
2. Valida que há **ao menos um item** na baixa
3. Muda o status para **solicitada**
4. Atualiza o status dos bens para **baixa_fisica_aguardando_aprovacao**
5. Envia **email de notificação** para os gestores

### Restrições

- Só pode enviar se status for **aguardando_envio**
- Deve ter ao menos **um item** (bem)

Somente usuários **Gestor de Patrimônio** ou **Operador de Inventário** podem executar esta operação.
""")

# API: /api/baixas-fisicas/{id}/aprovar/ (POST)
APROVAR_BAIXA_FISICA_DOC = dedent("""
Aprova a baixa física, autorizando a baixa definitiva dos bens.

### Comportamento

1. Valida que o status é **solicitada**
2. Valida permissões do usuário (apenas Gestor de Patrimônio)
3. Muda o status para **aceita**
4. **Gera número NBBPM** automaticamente
5. Registra **aprovador** e **data de aprovação**
6. Atualiza status dos bens para **baixa_fisica**
7. Atualiza **localização** dos bens com referência ao processo
8. Limpa **número do processo** de incorporação dos bens
9. Envia **email de notificação**

### Restrições

- Só pode aprovar se status for **solicitada**
- **Apenas Gestor de Patrimônio** pode executar esta ação

Após a aprovação, é possível gerar o PDF da Nota NBBPM.
""")

# API: /api/baixas-fisicas/{id}/cancelar/ (POST)
CANCELAR_BAIXA_FISICA_DOC = dedent("""
Cancela ou recusa a baixa física, restaurando o status dos bens.

### Comportamento

1. Valida que a baixa **não está aprovada**
2. Valida permissões do usuário (apenas Gestor de Patrimônio)
3. **Restaura** o status dos bens para **aprovado**
4. Muda o status da baixa para **recusada**
5. Envia **email de notificação**

### Parâmetros opcionais

- **motivo** (string) → motivo do cancelamento (opcional)

### Restrições

- **Não pode cancelar** baixas já aprovadas (status aceita)
- Só pode cancelar status **aguardando_envio** ou **solicitada**
- **Apenas Gestor de Patrimônio** pode executar esta ação

A ação é irreversível - não é possível reverter um cancelamento.
""")

# API: /api/baixas-fisicas/{id}/gerar-nbbpm/ (GET)
GERAR_NBBPM_DOC = dedent("""
Gera o arquivo PDF da Nota de Baixa de Bens Patrimoniais Móveis (NBBPM).

O PDF contém:

- Número NBBPM
- Número do processo de baixa física
- Unidade administrativa
- Lista completa de bens baixados
- Assinaturas e informações legais

### Restrições

- Só está disponível para baixas **aprovadas** (status aceita)
- A baixa deve ter **número NBBPM** gerado

### Retorno

O endpoint retorna um arquivo **PDF** pronto para download ou impressão.

O nome do arquivo segue o padrão: `NBBPM_{numero}.pdf`
""")

# API: /api/baixas-fisicas/exportar-excel/ (GET)
EXPORTAR_EXCEL_DOC = dedent("""
Exporta baixas físicas para arquivo Excel (.xlsx).

### Parâmetros opcionais

- **ids** → IDs separados por vírgula para exportar apenas específicas (ex: ?ids=1,2,3)

Todos os **filtros de listagem** também podem ser aplicados.

### Comportamento

1. Aplica filtros (se fornecidos)
2. Filtra por IDs (se fornecidos)
3. Aplica filtro de **escopo** (UAs do usuário)
4. Gera Excel com todas as baixas e seus bens
5. Retorna arquivo para download

### Formato do Excel

- **Cabeçalho** verde estilizado (padrão do sistema)
- **8 colunas**: UA, Nº Patrimonial, Nome do Bem, Status, NBBPM, Solicitante, Aprovador, Data
- **Uma linha para cada bem** de cada baixa
- **Ordenação** cronológica (mais recente primeiro)
- **Larguras** de coluna otimizadas
- **Formatação** profissional pronta para impressão

### Retorno

O endpoint retorna um arquivo **Excel** (.xlsx) pronto para download.

O nome do arquivo segue o padrão: `baixas_fisicas_{data}_{hora}.xlsx`

**Importante:** A exportação respeita o filtro de escopo - apenas baixas das UAs
do usuário serão incluídas.
""")
