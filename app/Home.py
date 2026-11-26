"""Visão geral: KPIs do último mês completo, principais achados e faturamento mensal.

Rodar com: uv run streamlit run app/Home.py
"""

import streamlit as st

from dados import calcular, consultar, referencia
from diagnostico import principais_achados, resumo_meses
from formatacao import (
    formatar_data,
    formatar_mes,
    formatar_moeda,
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
)
from graficos import barras_empilhadas, mostrar

st.set_page_config(page_title="Motopeças Analytics", page_icon="🏍️", layout="centered")

ref = referencia()
st.title("Motopeças")
st.caption(
    f"Diagnóstico dos dados de {formatar_data(ref.data_inicial)} a "
    f"{formatar_data(ref.data_referencia)} · loja e dados fictícios"
)

# ---- KPIs do último mês completo ----
meses = calcular("resumo_meses", resumo_meses)
atual, anterior = meses["atual"], meses["anterior"]
st.subheader(f"Resultado de {formatar_mes(atual['mes'])}")


def variacao(chave: str) -> str:
    """Variação percentual contra o mês anterior, com sinal (o st.metric colore pelo sinal)."""
    v = atual[chave] / anterior[chave] - 1
    return f"{'+' if v >= 0 else '-'}{formatar_pct(abs(v))} vs {formatar_mes(anterior['mes'])}"


col1, col2 = st.columns(2)
col1.metric(
    "Faturamento", formatar_moeda_curta(atual["faturamento"]), variacao("faturamento"), border=True
)
col2.metric(
    "Lucro bruto",
    formatar_moeda_curta(atual["lucro_bruto"]),
    variacao("lucro_bruto"),
    border=True,
    help="Faturamento menos o custo das peças vendidas.",
)
col1, col2 = st.columns(2)
pontos = (atual["margem_pecas_pct"] - anterior["margem_pecas_pct"]) * 100
col1.metric(
    "Margem das peças",
    formatar_pct(atual["margem_pecas_pct"]),
    f"{'+' if pontos >= 0 else '-'}{formatar_numero(abs(pontos), 1)} p.p.",
    border=True,
    help="p.p. = pontos percentuais: diferença direta entre duas porcentagens.",
)
col2.metric(
    "OS concluídas",
    atual["qtd_os"],
    variacao("qtd_os"),
    border=True,
    help="OS = ordem de serviço da oficina.",
)

# ---- Achados ----
st.subheader("O que os dados mostram")
for achado in calcular("principais_achados", principais_achados):
    st.markdown(f"- {achado}")

# ---- Faturamento mensal ----
st.subheader("Faturamento mensal")
fat = consultar("SELECT * FROM analise.faturamento_mensal ORDER BY mes")
rotulos = [formatar_mes(m) for m in fat.mes]
fig = barras_empilhadas(
    rotulos,
    {
        "Peças no balcão": fat.pecas_balcao.tolist(),
        "Peças na oficina": fat.pecas_oficina.tolist(),
        "Mão de obra": fat.mao_de_obra.tolist(),
    },
    completos=fat.mes_completo.tolist(),
)
tabela = fat.assign(
    Mês=rotulos,
    **{
        "Peças balcão": fat.pecas_balcao.map(formatar_moeda),
        "Peças oficina": fat.pecas_oficina.map(formatar_moeda),
        "Mão de obra": fat.mao_de_obra.map(formatar_moeda),
        "Total": fat.faturamento.map(formatar_moeda),
        "Mês completo": fat.mes_completo.map({True: "Sim", False: "Não"}),
    },
)[["Mês", "Peças balcão", "Peças oficina", "Mão de obra", "Total", "Mês completo"]]
mostrar(fig, tabela)
st.caption("Barras claras = mês incompleto (início ou fim do período de dados).")

# ---- Qualidade dos dados ----
with st.expander("Qualidade dos dados recebidos do sistema"):
    st.write(
        "Antes da análise, os dados exportados do ERP (sistema de gestão) passaram por limpeza. "
        "Isto foi o que precisou ser corrigido:"
    )
    qualidade = consultar(
        "SELECT problema AS Problema, quantidade AS Quantidade FROM analise.qualidade_dados"
    )
    st.dataframe(qualidade, hide_index=True)
