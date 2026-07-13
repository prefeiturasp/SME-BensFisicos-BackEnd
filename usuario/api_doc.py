from textwrap import dedent


# ==========================================
# DOCUMENTAÇÃO PARA A API "usuários"
# ==========================================

# API: /api/user/ (GET)
LIST_USERS_DOC = dedent("""
Retorna uma lista paginada de usuários cadastrados no sistema.

### Filtros disponíveis

- **is_staff** → retorna apenas membros da equipe
- **is_superuser** → retorna apenas superusuários
- **is_active** → filtra usuários ativos ou inativos
- **group_name** → filtra usuários por grupo
- **date_joined_after** → usuários criados após uma data
- **date_joined_before** → usuários criados antes de uma data
- **search** → busca usuários por nome
- **unidade** → busca usuários por código / nome / sigla da unidade administrativa
A resposta segue o padrão de paginação da API.
""")

# API: /api/user/ (POST)
CREATE_USERS_DOC = dedent("""
Cria um novo usuário no sistema.

Após a criação:

- `must_change_password` é automaticamente definido como **True**
- `last_password_change` recebe a data atual
- um registro é criado na tabela **HistoricoGeral**

Somente usuários administradores podem executar esta operação.
""")

# API: /api/user/{id}/ (GET)
RETRIEVE_USERS_DOC = dedent("""
Retorna todas as informações de um usuário específico.

O usuário é identificado pelo **ID** informado na URL.
""")

# API: /api/user/{id}/ (PUT)
UPDATE_USERS_DOC = dedent("""
Atualiza **todos os dados** de um usuário existente.

Caso a senha seja alterada:

- o campo `last_password_change` será atualizado automaticamente.

Todas as alterações são registradas na tabela **HistoricoGeral**.
""")

# API: /api/user/{id}/ (PATCH)
PATCH_USERS_DOC = dedent("""
Atualiza parcialmente os dados de um usuário.

Somente os campos enviados na requisição serão modificados.

As alterações também são registradas no **HistoricoGeral**.
""")

# API: /api/user/{id}/ (DELETE)
DELETE_USERS_DOC = dedent("""
Realiza o **soft delete** de um usuário.

Ao invés de remover o registro do banco:

- o campo **is_active** é alterado para **False**
- o evento é registrado no **HistoricoGeral**

Regras importantes:

- usuários **superusuários não podem ser desativados**
- usuários já desativados não podem ser desativados novamente
""")

# API: /api/user/{id}/restore (GET)
RESTORE_USERS_DOC = dedent("""
Reativa um usuário previamente desativado.

Este endpoint altera o campo **is_active** para **True**,
permitindo que o usuário volte a acessar o sistema.

A ação também gera um registro na tabela **HistoricoGeral**.
""")

# API: /api/user/exportar/ (GET)
EXPORT_USERS_DOC = dedent("""
Exporta os operadores visiveis para o usuario autenticado em formato Excel.

Regras de acesso:

- superusuario pode acessar o recurso;
- gestor de patrimonio pode acessar o recurso;
- operador de inventario nao acessa este recurso.

O arquivo exportado segue o padrao de colunas:

- Nome do Operador
- RF
- E-mail
- UA 1
- UA 2
- ...

Quando o usuario estiver vinculado a mais de uma Unidade Administrativa,
o arquivo cria colunas adicionais para cada vinculo.

O conteudo exportado sempre considera apenas usuarios do grupo de operador de
inventario.
""")
