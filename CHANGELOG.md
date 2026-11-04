# Changelog

Histórico anterior completo em [GitHub Releases](https://github.com/prefeiturasp/SME-BensFisicos-BackEnd/releases).

## Não lançado
- Padronização da estrutura: `.env.example` como modelo único. `requirements/` por ambiente. `docs/` mínima com Sphinx. `pyproject`, `pre-commit`, `Makefile` com alvos de qualidade e `sonar-project.properties`.
- Configurações com `settings/prod` incremental. Compose dev sem o serviço `db-init` e com verificação de saúde no `web`. Verificação de saúde pública em `/api/health/`. Documentação OpenAPI com grupos padronizados.
- Código conformado: `lint` e `typecheck` zerados. Suíte com 1522 testes após renomear `teste_nbbpm_lote.py` para `test_nbbpm_lote.py`. `init-db` exige as variáveis `SUPER_USER_*`.
- Remoções da etapa: pasta `scripts` mais `db_init.sql` desatualizado. `env.sample` como duplicata do `.env.example`. Arquivo único `requirements.txt` com os `Dockerfiles` apontando direto para `requirements/`.

## 2.7.0 - 2026-11-03
- Baixa física: edição do número do processo (#265), propagação da correção para bens vinculados (#267), rastreabilidade da alteração (#269), histórico com NBBPM vinculada (#272), bloqueio de baixa aberta e atualização de solicitante (#275).
- Baixa física (fluxo laudado): status laudado, evolução para baixa na geração da NBBPM e edição de baixa aceita sem NBBPM (#285).
- NBBPM: diálogo de confirmação no admin (#270), agrupamento sequencial de bens nos PDFs de CIMBPM/NTBPM/NBBPM (#271), retorno do backend para visualizar NBBPM (#273).
- Movimentações: busca de bens (#276), melhorias (#281), visualizar todas as movimentações (#284).
- Importação de documentos: padronização do número patrimonial, normalização e duplicados, prévia no dark-mode (#286).
- Validações e UX: múltiplas validações (#280), alerta contra descarte de alterações (#279), auditoria no histórico (#268).
