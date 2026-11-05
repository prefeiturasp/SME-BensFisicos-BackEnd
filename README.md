# Projeto de Gestão de Bens Patrimoniais

Backend Django do sistema de gestão patrimonial da Secretaria Municipal de Educação de São Paulo.

## Visão geral

O sistema é centrado no Django Admin e cobre o ciclo de vida de bens patrimoniais: cadastro, aprovação, movimentação entre unidades, baixa física e conciliação de inventário.

## Módulos ativos

- `usuario`: autenticação, perfis, recuperação/troca de senha, seleção de UA.
- `dados_comuns`: base compartilhada, contexto/auditoria, permissões e utilitários.
- `bem_patrimonial`: cadastro e gestão dos bens, movimentações, documentos (CIMBPM, NTBPM e NBBPM), baixa física.
- `inventario`: conciliação por UA e gestão de ocorrências.

## Perfis e permissões

- `GESTOR_PATRIMONIO`: acesso completo.
- `OPERADOR_INVENTARIO`: escopo restrito da sua unidade administrativa.

O provisionamento de grupos/permissões é feito por comando de gestão.

## Funcionalidades principais

- Cadastro e aprovação/reprovação de bens patrimoniais.
- Movimentação de bens com regras de bloqueio e aceite.
- Geração/consulta de documentos patrimoniais (CIMBPM, NTBPM e NBBPM).
- Fluxo de baixa física de bens.
- Transferência de bens entre unidades e secretarias.
- Importação de bens e conciliação de inventário por unidade administrativa.
- API REST com documentação OpenAPI.

## Stack

- Python 3.11
- Django 4.1.3
- Django Admin
- Django REST Framework + drf-spectacular
- PostgreSQL
- Docker / Docker Compose

## Setup rápido (Docker)

1. Copie o arquivo de ambiente:

   ```bash
   cp .env.example .env
   ```

2. Suba o ambiente de desenvolvimento:

   ```bash
   docker compose -f docker-compose-dev.yml up -d
   ```

3. Rode migrações e crie usuário admin inicial (exige `SUPER_USER`, `SUPER_USER_PASSWORD` e `SUPER_USER_EMAIL` no `.env`):

   ```bash
   make init-db
   ```

4. Provisione grupos e permissões:

   ```bash
   make setup-grupos-permissoes
   ```

## Setup local (sem Docker)

1. Crie e ative o ambiente virtual:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Instale dependências:

   ```bash
   pip install -r requirements/local.txt
   ```

3. Configure `.env` e execute migrações:

   ```bash
   python manage.py migrate
   ```

4. Provisione grupos/permissões:

   ```bash
   python manage.py setup_grupos_e_permissoes
   ```

5. Crie superusuário e suba servidor:

   ```bash
   python manage.py createsuperuser
   python manage.py runserver
   ```

## Comandos úteis

Veja todos com `make help`. Os principais:

- `make test` - suíte completa via pytest em container
- `make lint` - black + ruff
- `make typecheck` - mypy
- `make coverage` - relatório de cobertura
- `make schema` - gera o OpenAPI em `docs/_build/schema.yml`
- `make docs` - gera a documentação Sphinx em `docs/_build/html`
- `make quality` - executa lint, typecheck, testes e docs em sequência
- `make migrate` - aplica migrations no banco local
- `make shell` - shell Django no container

Para outros casos use `docker compose -f docker-compose-dev.yml run --rm web ...`.

## Google Analytics no Django Admin

O Django Admin renderiza o snippet do Google Analytics apenas em produção, quando `DJANGO_DEBUG=False`.

O ID do Google Analytics está fixado no código do backend. No ambiente local, mantenha `DJANGO_DEBUG=True` para evitar carregamento do script durante desenvolvimento.

## Endpoints principais

- `GET /api/health/` - verificação de saúde (pública)
- `GET /api/docs/` - Swagger UI
- `GET /api/redoc/` - ReDoc
- `GET /api/schema/` - OpenAPI schema
- `GET|POST /api/bens/...` - cadastro e gestão de bens
- `GET|POST /api/baixa-fisica/...` - fluxo de baixa física
- `GET|POST /api/nbbpm/...` - NBBPM unificada
- `GET|POST /api/transferencias/...` - transferências entre unidades e secretarias
- `GET|POST /api/movimentacoes/...` - movimentações de bens
- `GET|POST /api/inventario/...` - conciliação de inventário
- `GET /api/unidades-administrativas/...` - unidades administrativas
- `GET /api/unidades-orcamentarias/...` - unidades orçamentárias
- `POST /api/auth/...` - autenticação
- `POST /api/user/...` - gerenciamento de usuários
- `GET /documento-cimbpm/<pk>/download/` - download protegido de CIMBPM
- `GET /documento-ntbpm/<pk>/download/` - download protegido de NTBPM

## Módulo removido: agendamento de suporte

O módulo `agendamento_suporte` foi descontinuado e removido do código-fonte.
