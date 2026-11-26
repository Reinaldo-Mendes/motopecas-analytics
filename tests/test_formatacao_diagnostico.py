"""Testes da formatação brasileira e dos textos do diagnóstico."""

import re
from datetime import date

import pandas as pd
import pytest

from diagnostico import (
    principais_achados,
    resumo_estoque,
    resumo_meses,
    resumo_troca_oleo,
    troca_oleo_semana,
)
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


def test_achados_estruturados_e_ordenados_pelo_impacto(con):
    achados = principais_achados(con)
    assert len(achados) >= 8
    assert {a.tipo for a in achados} <= {"alerta", "oportunidade", "info"}
    assert {a.pagina for a in achados} <= {"estoque", "vendas", "oficina", "clientes"}
    com_impacto = [a for a in achados if a.tipo != "info"]
    assert achados[: len(com_impacto)] == com_impacto  # contexto sempre no fim
    impactos = [a.impacto for a in com_impacto]
    assert impactos == sorted(impactos, reverse=True)
    textos = [f"{a.valor} {a.texto}" for a in achados]
    assert not any(re.search(r"\d\.\d mil", t) for t in textos)  # nada de '1.0 mil'
    assert not any("None" in t or "nan" in t for t in textos)


def test_troca_de_oleo_da_semana(con):
    lista = troca_oleo_semana(con, limite=None)
    resumo = resumo_troca_oleo(con)
    assert len(lista) == resumo["qtd_esta_semana"] + resumo["qtd_atrasada"]
    assert all(-15 <= c["dias_para_troca"] <= 7 for c in lista)
    assert len(troca_oleo_semana(con, limite=3)) == 3
