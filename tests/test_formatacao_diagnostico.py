"""Testes da formatação brasileira e dos textos do diagnóstico."""

import re
from datetime import date

import pandas as pd
import pytest

from diagnostico import principais_achados, resumo_estoque, resumo_meses
from formatacao import (
    formatar_data,
    formatar_mes,
    formatar_moeda,
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
    formatar_telefone,
)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(1234.56, "R$ 1.234,56"), (0, "R$ 0,00"), (-10, "-R$ 10,00"), (1_000_000, "R$ 1.000.000,00")],
)
def test_formatar_moeda(valor, esperado):
    assert formatar_moeda(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(950, "R$ 950"), (12_345, "R$ 12,3 mil"), (1_234_567, "R$ 1,2 mi"), (-4_000, "-R$ 4,0 mil")],
)
def test_formatar_moeda_curta(valor, esperado):
    assert formatar_moeda_curta(valor) == esperado


def test_formatar_numero_pct_data_mes():
    assert formatar_numero(1234567.8) == "1.234.568"
    assert formatar_pct(0.3934) == "39,3%"
    assert formatar_data(date(2026, 11, 26)) == "26/11/2026"
    assert formatar_data(None) == ""
    assert formatar_data(pd.NaT) == ""
    assert formatar_mes(date(2026, 3, 1)) == "mar/2026"


def test_formatar_telefone():
    assert formatar_telefone("35912345678") == "(35) 91234-5678"
    assert formatar_telefone(None) == "sem telefone"


def test_resumo_meses_usa_so_meses_completos(con):
    meses = resumo_meses(con)
    assert meses["atual"]["mes"] == date(2026, 10, 1)  # novembro/2026 está pela metade
    assert meses["anterior"]["mes"] == date(2026, 9, 1)


def test_resumo_estoque_consistente(con):
    estoque = resumo_estoque(con)
    assert 0 < estoque["valor_parado"] < estoque["valor_total"]
    assert estoque["qtd_em_falta_a"] <= estoque["qtd_em_falta"]


def test_achados_sao_frases_formatadas(con):
    achados = principais_achados(con)
    assert len(achados) >= 5
    assert achados[0].startswith("R$ ")
    assert not any(re.search(r"\d\.\d mil", a) for a in achados)  # nada de '1.0 mil'
