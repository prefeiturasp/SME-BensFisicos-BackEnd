COMPOSE_DEV ?= docker compose -f docker-compose-dev.yml
# Roda como o usuário do host para não gerar arquivos como root no volume montado
# (a imagem dev usa usuário não-root).
RUN_USER ?= --user $(shell id -u):$(shell id -g)
RUN_WEB = $(COMPOSE_DEV) run --rm $(RUN_USER) web
RUN_WEB_NODEPS = $(COMPOSE_DEV) run --rm --no-deps $(RUN_USER) web
PYTEST_ARGS ?= -q -p no:cacheprovider

.PHONY: help ensure-env up down logs shell migrate init-db seed-base setup-grupos-permissoes test coverage lint typecheck schema docs docs-clean precommit quality clean-local

help:
	@echo "Uso: make <alvo>"
	@echo ""
	@echo "Ambiente:"
	@echo "  make up           - sobe ambiente de desenvolvimento"
	@echo "  make down         - derruba o ambiente docker local sem apagar volumes"
	@echo "  make logs         - acompanha logs do servico web"
	@echo "  make shell        - abre shell Django via container dev"
	@echo ""
	@echo "Banco e app:"
	@echo "  make init-db      - migrate + cria superusuario (uso local)"
	@echo "  make migrate      - aplica migrations no banco do compose dev"
	@echo "  make seed-base    - massa de demonstracao (opcional)"
	@echo "  make setup-grupos-permissoes - provisiona grupos e permissoes"
	@echo "  make schema       - gera schema OpenAPI em docs/_build/schema.yml"
	@echo ""
	@echo "Qualidade:"
	@echo "  make test         - executa pytest em container com Postgres"
	@echo "  make coverage     - gera relatorio de coverage"
	@echo "  make lint         - executa black --check e ruff"
	@echo "  make typecheck    - executa mypy"
	@echo "  make docs         - gera documentacao Sphinx"
	@echo "  make docs-clean   - remove artefatos de docs"
	@echo "  make precommit    - executa os hooks do pre-commit em container"
	@echo "  make quality      - executa lint, typecheck, test e docs"
	@echo ""
	@echo "Limpeza:"
	@echo "  make clean-local  - remove artefatos locais temporarios"

ensure-env:
	@test -f .env || cp .env.example .env

up: ensure-env
	$(COMPOSE_DEV) up --build

down:
	$(COMPOSE_DEV) down

logs: ensure-env
	$(COMPOSE_DEV) logs -f web

shell: ensure-env
	$(RUN_WEB) python manage.py shell

migrate: ensure-env
	$(RUN_WEB) python manage.py migrate --noinput

init-db:
	docker compose -f docker-compose-dev.yml run --rm web python manage.py migrate
	docker compose -f docker-compose-dev.yml run --rm web python manage.py shell -c "import os, sys; u=os.getenv('SUPER_USER'); p=os.getenv('SUPER_USER_PASSWORD'); e=os.getenv('SUPER_USER_EMAIL'); (u and p and e) or sys.exit('Defina SUPER_USER, SUPER_USER_PASSWORD e SUPER_USER_EMAIL no .env'); from django.contrib.auth import get_user_model; User=get_user_model(); User.objects.filter(username=u).exists() or User.objects.create_superuser(username=u,email=e,password=p)"
seed-base:
	docker compose -f docker-compose-dev.yml run --rm web python manage.py seed_bensfisicos_demo
setup-grupos-permissoes:
	docker compose -f docker-compose-dev.yml run --rm web python manage.py setup_grupos_e_permissoes

test: ensure-env
	$(RUN_WEB) python -m pytest $(PYTEST_ARGS)

coverage: ensure-env
	$(RUN_WEB) sh -c 'rm -rf docs/_cov && COVERAGE_FILE=/tmp/.coverage python -m coverage erase && COVERAGE_FILE=/tmp/.coverage python -m coverage run --source=. -m pytest $(PYTEST_ARGS) && COVERAGE_FILE=/tmp/.coverage python -m coverage report -m && COVERAGE_FILE=/tmp/.coverage python -m coverage html -d docs/_cov && COVERAGE_FILE=/tmp/.coverage python -m coverage xml -o coverage.xml'

lint: ensure-env
	$(RUN_WEB_NODEPS) sh -c 'RUFF_CACHE_DIR=/tmp/.ruff_cache python -m black --check bem_patrimonial usuario inventario dados_comuns config manage.py && RUFF_CACHE_DIR=/tmp/.ruff_cache python -m ruff check bem_patrimonial usuario inventario dados_comuns config manage.py'

typecheck: ensure-env
	$(RUN_WEB_NODEPS) python -m mypy --cache-dir /tmp/.mypy_cache bem_patrimonial usuario inventario dados_comuns config

schema: ensure-env
	$(RUN_WEB_NODEPS) sh -c 'mkdir -p docs/_build && python manage.py spectacular --file docs/_build/schema.yml'

docs: ensure-env
	$(RUN_WEB_NODEPS) sh -c 'rm -rf docs/_build/html docs/_build/doctrees && python -m sphinx -b html docs docs/_build/html'

docs-clean:
	rm -rf docs/_build docs/_cov

precommit: ensure-env
	$(RUN_WEB_NODEPS) sh -c 'export HOME=/tmp PRE_COMMIT_HOME=/tmp/.pre-commit-cache && git config --global --add safe.directory /code && python -m pre_commit run --files $$(find bem_patrimonial usuario inventario dados_comuns config docs -type f) .env.example .gitignore .pre-commit-config.yaml Dockerfile Dockerfile.dev docker-compose-dev.yml pyproject.toml README.md CHANGELOG.md Makefile manage.py'
	@echo "precommit ok: black e ruff verdes"

quality: lint typecheck test docs
	@echo "quality ok: lint, typecheck, test e docs verdes"

clean-local:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache htmlcov docs/_build docs/_cov bens_fisicos_backend.egg-info .coverage db.sqlite3
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
