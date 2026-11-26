"""Visão geral: KPIs do último mês completo, o que fazer na semana e os achados do diagnóstico."""

import streamlit as st

from componentes import cabecalho, grade_de_cartoes, link_pagina, secao
from dados import calcular, consultar, referencia
from diagnostico import (
    principais_achados,
    resumo_clientes,
    resumo_estoque,
    resumo_meses,
    resumo_troca_oleo,
)
from formatacao import (
    formatar_data,
    formatar_mes,
    formatar_moeda,
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
)
from graficos import barras_empilhadas, mostrar

ref = referencia()
cabecalho(
    "Motopeças",
    f"Diagnóstico dos dados de {formatar_data(ref.data_inicial)} a "
    f"{formatar_data(ref.data_referencia)}",
)
st.badge("Loja e dados fictícios", icon=":material/science:", color="gray")

# ---- KPIs do último mês completo, com a tendência dos últimos 12 meses ----
meses = calcular("resumo_meses", resumo_meses)
atual, anterior = meses["atual"], meses["anterior"]
historico = consultar(
    "SELECT * FROM analise.faturamento_mensal WHERE mes_completo ORDER BY mes DESC LIMIT 12"
).iloc[::-1]
secao(f"Resultado de {formatar_mes(atual['mes'])}", "Minigráfico: últimos 12 meses completos.")


def variacao(chave: str) -> str:
    """Variação percentual contra o mês anterior, com sinal (o st.metric colore pelo sinal)."""
    v = atual[chave] / anterior[chave] - 1
    return f"{'+' if v >= 0 else '-'}{formatar_pct(abs(v))} vs {formatar_mes(anterior['mes'])}"


col1, col2 = st.columns(2)
col1.metric(
    "Faturamento",
    formatar_moeda_curta(atual["faturamento"]),
    variacao("faturamento"),
    border=True,
    chart_data=historico.faturamento.tolist(),
    chart_type="area",
)
col2.metric(
    "Lucro bruto",
    formatar_moeda_curta(atual["lucro_bruto"]),
    variacao("lucro_bruto"),
    border=True,
    chart_data=historico.lucro_bruto.tolist(),
    chart_type="area",
    help="Faturamento menos o custo das peças vendidas.",
)
col1, col2 = st.columns(2)
pontos = (atual["margem_pecas_pct"] - anterior["margem_pecas_pct"]) * 100
col1.metric(
    "Margem das peças",
    formatar_pct(atual["margem_pecas_pct"]),
    f"{'+' if pontos >= 0 else '-'}{formatar_numero(abs(pontos), 1)} p.p.",
    delta_color="normal" if abs(pontos) >= 0.05 else "off",  # 0,0 p.p. não é alta
    delta_arrow="auto" if abs(pontos) >= 0.05 else "off",
    border=True,
    chart_data=(historico.margem_pecas_pct * 100).tolist(),
    chart_type="line",
    help="p.p. = pontos percentuais: diferença direta entre duas porcentagens.",
)
col2.metric(
    "OS concluídas",
    formatar_numero(atual["qtd_os"]),
    variacao("qtd_os"),
    border=True,
    chart_data=historico.qtd_os.tolist(),
    chart_type="line",
    help="OS = ordem de serviço da oficina.",
)

# ---- O que fazer esta semana ----
secao("Para fazer esta semana")
oleo = calcular("resumo_troca_oleo", resumo_troca_oleo)
clientes = calcular("resumo_clientes", resumo_clientes)
estoque = calcular("resumo_estoque", resumo_estoque)
qtd_oleo = oleo["qtd_esta_semana"] + oleo["qtd_atrasada"]
with st.container(border=True):
    link_pagina(
        "clientes",
        f"Troca de óleo: chamar {qtd_oleo} clientes",
        ":material/oil_barrel:",
    )
    link_pagina(
        "clientes",
        f"Ligar para {formatar_numero(clientes['em_risco'])} clientes sumindo",
        ":material/call:",
    )
    link_pagina(
        "estoque",
        f"Comprar {estoque['qtd_em_falta']} itens em falta",
        ":material/shopping_cart:",
    )

# ---- Achados ----
achados = calcular("principais_achados", principais_achados)
com_impacto = [a for a in achados if a.tipo != "info"]
contexto = [a for a in achados if a.tipo == "info"]
secao("Onde está o dinheiro", "Do maior impacto em R$ para o menor.")
grade_de_cartoes(com_impacto)
secao("Contexto")
grade_de_cartoes(contexto)

# ---- Faturamento mensal ----
secao("Faturamento mensal", "Barras claras = mês incompleto (início ou fim dos dados).")
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

# ---- Qualidade dos dados ----
with st.expander("Qualidade dos dados recebidos do sistema", icon=":material/fact_check:"):
    st.write(
        "Antes da análise, os dados exportados do ERP (sistema de gestão) passaram por limpeza. "
        "Isto foi o que precisou ser corrigido:"
    )
    qualidade = consultar(
        "SELECT problema AS Problema, quantidade AS Quantidade FROM analise.qualidade_dados"
    )
    st.dataframe(qualidade, hide_index=True)
