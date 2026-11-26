"""Acesso ao banco analítico para as páginas do dashboard."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))  # para importar pipeline, formatacao e diagnostico

from pipeline import CAMINHO_BANCO, construir_banco  # noqa: E402


@st.cache_resource(show_spinner="Preparando os dados pela primeira vez...")
def garantir_banco() -> Path:
    """Monta o banco a partir dos CSVs se ele ainda não existir (ex.: no primeiro deploy)."""
    if not CAMINHO_BANCO.exists():
        construir_banco()
    return CAMINHO_BANCO


@st.cache_data(ttl=3600)
def consultar(sql: str) -> pd.DataFrame:
    """Executa uma consulta só de leitura e guarda o resultado em cache por 1 hora."""
    with duckdb.connect(garantir_banco(), read_only=True) as con:
        return con.execute(sql).df()


@st.cache_data(ttl=3600)
def calcular(nome: str, _funcao: Callable):
    """Roda uma função de `diagnostico` (que recebe a conexão) com cache.

    O cache usa só `nome` como chave: parâmetros com `_` na frente o Streamlit não tenta hashear.
    """
    with duckdb.connect(garantir_banco(), read_only=True) as con:
        return _funcao(con)


def referencia() -> pd.Series:
    """Datas inicial e de referência ("hoje") dos dados."""
    return consultar("SELECT * FROM analise.referencia").iloc[0]
