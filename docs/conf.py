"""Configuração Sphinx do projeto."""

project = "SME Bens Físicos Backend"
author = "SME"
release = "2.7.0"

extensions: list[str] = ["myst_parser"]
source_suffix = {
    ".md": "markdown",
}
templates_path: list[str] = ["_templates"]
exclude_patterns: list[str] = ["_build", "_cov"]
language = "pt_BR"
