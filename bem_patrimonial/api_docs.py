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
  - `url_solicitar` → se status for aguardando_envio
  - `url_aprovar` → se status for solicitada
  - `url_recusar` → se status for aguardando_envio ou solicitada
  - `url_gerar_nbbpm` → se status for aceita e tiver número NBBPM
""")

# API: /api/baixas-fisicas/{id}/ (PUT/PATCH)
UPDATE_BAIXAS_FISICAS_DOC = dedent("""
Atualiza os dados de uma baixa física existente.

### Restrições importantes

- Somente baixas com status **aguardando_envio** podem ser editadas
- Após a criação, apenas a lista de **itens** pode ser alterada
- Não é possível alterar **unidade administrativa**, **número do processo** ou **data da baixa**

### Gerenciamento de itens

Ao atualizar a lista de itens, a API trata o payload como a lista final desejada:

- **Bens enviados** e já presentes → são mantidos
- **Bens enviados** e ainda não presentes → são incluídos
- **Bens não enviados** → são removidos

O status dos bens é ajustado automaticamente conforme inclusão/remoção de itens.

Todas as alterações são aplicadas de forma transacional (tudo ou nada).
""")

# API: /api/baixas-fisicas/{id}/solicitar/ (POST)
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

# API: /api/baixas-fisicas/{id}/recusar/ (POST)
CANCELAR_BAIXA_FISICA_DOC = dedent("""
Recusa a baixa física, restaurando o status dos bens.

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

IMPORTAR_BENS_DOC = dedent("""
Importa bens patrimoniais em lote a partir de uma planilha.
 
O arquivo deve ser enviado como `multipart/form-data` no campo `arquivo`.
 
### Formatos aceitos
 
- **XLSX** (recomendado)
- **XLS**
- **CSV** (UTF-8 ou Latin-1)
 
Tamanho máximo: **10 MB**.
 
---
 
### Colunas esperadas na planilha
 
O cabeçalho aceita variações de caixa e acentuação
(ex: `Número Patrimonial`, `NUMERO PATRIMONIAL`, `numero_patrimonial`).
 
| Coluna | Observações |
|---|---|
| `numero_patrimonial` | Vazio = bem sem numeração |
| `nome` | |
| `descricao` | |
| `marca` | |
| `modelo` | |
| `valor_unitario` | Formato: `0,00` ou `0.000,00` |
| `numero_processo` | |
| `localizacao` | |
 
---
 
### Regras de negócio
 
- A **Unidade Administrativa** e a **Unidade Orçamentária** dos bens importados
  são sempre as do usuário autenticado. Qualquer coluna UA na planilha é ignorada.
- O usuário deve ter uma UA ativa vinculada ao perfil. Caso contrário,
  a carga inteira é rejeitada com `403` antes de processar qualquer linha.
- Todos os bens criados entram com status **Aguardando Aprovação**.
- Linhas com `numero_patrimonial` duplicado (dentro do arquivo ou já no banco)
  são **ignoradas individualmente** — as demais linhas são salvas normalmente.
- `sem_numeracao` e `numero_formato_antigo` são inferidos automaticamente.
 
---
 
### Retornos HTTP
 
#### `201 Created` — todos os bens importados sem erros
 
```json
{
  "detail": "42 bem(ns) importado(s) com sucesso.",
  "importados": 42,
  "ignorados_com_erro": 0,
  "total_linhas": 42
}
```
 
#### `207 Multi-Status` — importação parcial (alguns importados, alguns com erro)
 
```json
{
  "detail": "38 bem(ns) importado(s) com sucesso. 4 linha(s) com erro foram ignoradas.",
  "importados": 38,
  "ignorados_com_erro": 4,
  "total_linhas": 42,
  "erros_por_linha": [
    "Linha 5 | Número Patrimonial: 001.000000001-0 | Erro: Número patrimonial já cadastrado no sistema.",
    "Linha 12 | Número Patrimonial: 001.000000002-0 | Erro: Número patrimonial duplicado no arquivo. Primeira ocorrência na linha 3."
  ]
}
```
 
#### `400 Bad Request` — arquivo ausente, formato inválido ou tamanho excedido
 
```json
{
  "detail": "Arquivo inválido.",
  "erros": {
    "arquivo": ["Formato de arquivo não suportado: 'planilha.txt'. Use XLSX, XLS ou CSV."]
  }
}
```
 
#### `403 Forbidden` — usuário sem UA vinculada ou UA inativa
 
```json
{
  "detail": "Não é possível importar bens: seu usuário não possui uma Unidade Administrativa vinculada. Entre em contato com o gestor de patrimônio."
}
```
 
#### `422 Unprocessable Entity` — planilha vazia, ilegível ou todas as linhas com erro
 
```json
{
  "detail": "Nenhum bem foi importado. Todas as linhas contêm erros. Corrija o arquivo e tente novamente.",
  "importados": 0,
  "ignorados_com_erro": 42,
  "total_linhas": 42,
  "erros_por_linha": ["Linha 1 | Número Patrimonial: 001.000000001-0 | Erro: ..."]
}
```
 
#### `500 Internal Server Error` — erro inesperado durante o processamento
 
```json
{
  "detail": "Erro inesperado durante a importação.",
  "erro": "descrição técnica do erro"
}
```
 
---
 
### Observações
 
- Mesmo com erros parciais (`207`), os bens válidos **já foram persistidos**.
  Não há rollback das linhas bem-sucedidas.
- A rota não suporta dry-run via API. Use o Admin Django para pré-visualizar.
 
Somente usuários com permissão de criação de bens patrimoniais podem usar este endpoint.
""")

# API: /api/baixas-fisicas/:id/solicitar-correcao/ (POST)
SOLICITAR_CORRECAO_DOC = dedent("""
Solicita correção de uma baixa física, devolvendo-a ao solicitante original.
 
### Quando usar
 
O Gestor utiliza este endpoint ao revisar uma baixa com status **Solicitada**
e identificar que um ou mais itens precisam de ajuste antes da aprovação.
 
### Diferença em relação a `recusar`
 
- **`recusar`**: encerra definitivamente o processo (status → Recusada).
- **`solicitar-correcao`**: devolve a baixa para edição (status →
  Em elaboração), permitindo que o solicitante ajuste os itens e
  reenvie para nova análise.
 
### Parâmetros obrigatórios
 
- **motivo** → texto livre com as orientações sobre o que precisa ser
  corrigido (obrigatório, não pode ser vazio)
 
### Comportamento

 1. Valida que o status atual da baixa é **Solicitada**
 2. Valida que o usuário é Gestor de Patrimônio, superuser **ou o solicitante (criado_por)** — permite withdraw pelo operador
 3. Altera o status da baixa para **Em elaboração**
4. Registra o motivo no histórico da baixa
5. Notifica o solicitante original por e-mail (melhor esforço,
   falhas de envio não impedem a operação)
 
### Retorno
 
Retorna o objeto **BaixaFisicaBemPatrimonialDetailSerializer** atualizado,
já refletindo o novo status.
 
**Importante:** este endpoint só pode ser chamado a partir do status
Solicitada. Para baixas em outros status, a API retorna erro de validação.
""")
