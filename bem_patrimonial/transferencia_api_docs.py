from textwrap import dedent


LIST_TRANSFERENCIAS_DOC = dedent(
    """
    Retorna uma lista paginada de transferências de bens patrimoniais.

    ### Filtros disponíveis

    - **search** → busca por número NTBPM, número do processo, códigos/nomes/siglas
      das UOs de origem e destino, além de número patrimonial e nome dos bens
    - **numero_ntbpm** → filtra por número NTBPM
    - **numero_processo** → filtra por número do processo
    - **nome_bem** → filtra pelo nome do bem
    - **unidade_orcamentaria_origem** → filtra pela UO de origem
    - **unidade_orcamentaria_destino** → filtra pela UO de destino

    ### Ordenação disponível

    - **id**
    - **numero_ntbpm**
    - **numero_processo**
    - **criado_em**
    - **atualizado_em**
    - **unidade_orcamentaria_origem__codigo**
    - **unidade_orcamentaria_destino__codigo**

    Use `-` antes do campo para ordem decrescente.

    A resposta segue o padrão de paginação da API.

    **Importante:** o usuário visualiza apenas transferências que pertencem ao
    escopo da sua UO, seguindo a mesma regra do Django Admin.
    """
)


CREATE_TRANSFERENCIA_DOC = dedent(
    """
    Cria uma nova transferência de bens patrimoniais.

    Após a criação:

    - a UO de origem é derivada automaticamente do usuário autenticado
    - a UO de destino deve ser externa à SME
    - a UA de destino é resolvida automaticamente para o ponto central da UO
      escolhida
    - os bens informados são transferidos imediatamente e recebem o status
      **Transferido**
    - o sistema gera automaticamente o número NTBPM

    ### Validações aplicadas

    - é obrigatório informar ao menos um bem
    - a UO de destino precisa ser externa à SME
    - a UO de destino deve possuir ponto central cadastrado
    - todos os bens precisam estar com status **Aprovado**
    - todos os bens precisam pertencer à UO de origem do usuário

    Somente usuários **Gestor de Patrimônio** podem executar esta operação.
    """
)


RETRIEVE_TRANSFERENCIA_DOC = dedent(
    """
    Retorna todas as informações de uma transferência específica.

    A resposta inclui:

    - dados completos da transferência
    - lista de itens transferidos
    - URL protegida para download do documento NTBPM, quando disponível
    """
)


OPCOES_CADASTRO_TRANSFERENCIA_DOC = dedent(
    """
    Lista UOs externas ativas que podem ser usadas como destino na
    transferência de bens.

    O retorno inclui um indicador informando se a UO possui ponto central
    cadastrado.
    """
)
