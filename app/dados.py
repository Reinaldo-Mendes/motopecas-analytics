"""Acesso ao banco analítico para as páginas do dashboard."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:  # o módulo é relido a cada interação (ver Home.py)
    sys.path.insert(0, str(RAIZ / "src"))  # para importar pipeline, formatacao e diagnostico

from pipeline import CAMINHO_BANCO, banco_atualizado, construir_banco  # noqa: E402


def versao_dos_arquivos() -> tuple:
    """Nome, data de modificação e tamanho dos CSVs, SQL e módulos de src/.

    É barato (só lê os metadados dos arquivos) e muda sempre que um push altera dados ou código.
    Entra na chave dos caches abaixo: arquivo mudou = cache antigo deixa de ser usado.
    """
    arquivos = [*(RAIZ / "data" / "raw").glob("*.csv"), *(RAIZ / "src").rglob("*.sql")]
    arquivos += (RAIZ / "src").glob("*.py")
    return tuple(sorted((str(a), a.stat().st_mtime_ns, a.stat().st_size) for a in arquivos))


@st.cache_resource(show_spinner="Preparando os dados...")
def garantir_banco(versao: tuple = ()) -> Path:
    """Monta o banco se ele não existir ou tiver sido feito com CSVs/SQL antigos.

    No Streamlit Cloud o arquivo .duckdb sobrevive a um novo deploy: sem essa checagem, código
    novo leria um banco velho (sem as views novas). Roda uma vez para cada `versao` dos arquivos.
    """
    if not banco_atualizado():
        construir_banco()
    return CAMINHO_BANCO


@st.cache_data(ttl=3600)
def _consultar(sql: str, versao: tuple) -> pd.DataFrame:
    with duckdb.connect(garantir_banco(versao=versao), read_only=True) as con:
        return con.execute(sql).df()


def consultar(sql: str) -> pd.DataFrame:
    """Executa uma consulta só de leitura, com cache de 1 hora (ou até os arquivos mudarem)."""
    return _consultar(sql, versao_dos_arquivos())


@st.cache_data(ttl=3600)
def _calcular(nome: str, versao: tuple, _funcao: Callable):
    with duckdb.connect(garantir_banco(versao=versao), read_only=True) as con:
        return _funcao(con)


def calcular(nome: str, funcao: Callable):
    """Roda uma função de `diagnostico` (que recebe a conexão) com cache.

    A chave do cache é o `nome` + a versão dos arquivos: parâmetros com `_` na frente o
    Streamlit não tenta hashear (uma função não dá para comparar de forma confiável).
    """
    return _calcular(nome, versao_dos_arquivos(), funcao)


def referencia() -> pd.Series:
    """Datas inicial e de referência ("hoje") dos dados."""
    return consultar("SELECT * FROM analise.referencia").iloc[0]
