# Changelog

Histórico anterior completo em [GitHub Releases](https://github.com/prefeiturasp/SME-BensFisicos-BackEnd/releases).

## Não lançado
- Lote 1 da padronização (estrutura segura): criado `.env.example` e enxugado `.gitignore`.
- Criados `CHANGELOG.md` e `sonar-project.properties` como base da padronização.

## 2.7.0 - 2026-11-03
- Baixa física: edição do número do processo (#265), propagação da correção para bens vinculados (#267), rastreabilidade da alteração (#269), histórico com NBBPM vinculada (#272), bloqueio de baixa aberta e atualização de solicitante (#275).
- Baixa física (fluxo laudado): status laudado, evolução para baixa na geração da NBBPM e edição de baixa aceita sem NBBPM (#285).
- NBBPM: diálogo de confirmação no admin (#270), agrupamento sequencial de bens nos PDFs de CIMBPM/NTBPM/NBBPM (#271), retorno do backend para visualizar NBBPM (#273).
- Movimentações: busca de bens (#276), melhorias (#281), visualizar todas as movimentações (#284).
- Importação de documentos: padronização do número patrimonial, normalização e duplicados, prévia no dark-mode (#286).
- Validações e UX: múltiplas validações (#280), alerta contra descarte de alterações (#279), auditoria no histórico (#268).
