"""Oficina: volume, orçamentos recusados, produção e prazo por mecânico, serviços e venda casada."""

import streamlit as st

from componentes import cabecalho, secao
from dados import calcular, consultar
from diagnostico import resumo_cancelamentos
from formatacao import (
    formatar_mes,
    formatar_moeda,
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
)
from graficos import NEUTRO, SERIES, barras_horizontais, linha, mostrar

cabecalho("Oficina", "OS (ordens de serviço): volume, recusas, prazo e o que vender junto.")

periodo = (
    st.segmented_control(
        "Período", ["Últimos 12 meses", "Últimos 24 meses"], default="Últimos 12 meses"
    )
    or "Últimos 12 meses"
)
dias = 365 if periodo == "Últimos 12 meses" else 730
os_ = consultar(f"""
    SELECT * FROM analise.ordens_concluidas
    WHERE data_abertura > (SELECT data_referencia FROM analise.referencia) - {dias}
""")

col1, col2 = st.columns(2)
col1.metric("OS concluídas", formatar_numero(len(os_)), border=True, help="OS = ordem de serviço.")
col2.metric(
    "Ticket médio da OS",
    formatar_moeda(os_.valor_total.mean()),
    border=True,
    help="Peças + mão de obra, em média por OS.",
)
col1, col2 = st.columns(2)
col1.metric("Mão de obra faturada", formatar_moeda_curta(os_.valor_mao_obra.sum()), border=True)
col2.metric(
    "Tempo médio na oficina",
    f"{formatar_numero(os_.dias_na_oficina.mean(), 1)} dias",
    border=True,
    help="Da abertura à conclusão da OS.",
)

# ---- OS por mês ----
secao("OS concluídas por mês", "Só meses completos.")
mensal = consultar(f"""
    SELECT m.mes, m.qtd_os, m.mes_completo
    FROM analise.faturamento_mensal AS m
    WHERE m.mes_completo
      AND m.mes > (SELECT date_trunc('month', data_referencia) FROM analise.referencia)
                  - INTERVAL {dias // 30} MONTH
    ORDER BY m.mes
""")
rotulos = [formatar_mes(m) for m in mensal.mes]
mostrar(
    linha(
        rotulos, mensal.qtd_os.tolist(), "OS", rotulo_final=formatar_numero(mensal.qtd_os.iloc[-1])
    ),
    mensal.assign(Mês=rotulos, OS=mensal.qtd_os)[["Mês", "OS"]],
)

# ---- Orçamentos recusados (sempre 12 meses) ----
secao(
    "Orçamentos recusados",
    "Últimos 12 meses. OS cancelada = o cliente não aprovou o orçamento.",
)
cancel = calcular("resumo_cancelamentos", resumo_cancelamentos)
col1, col2 = st.columns(2)
col1.metric(
    "Deixou de entrar",
    formatar_moeda_curta(cancel["valor_perdido"]),
    f"{formatar_numero(cancel['qtd_canceladas'])} OS canceladas",
    delta_color="off",
    delta_arrow="off",
    border=True,
    help="Mão de obra + peças orçadas nas OS canceladas.",
)
col2.metric(
    "Recusa acima de R$ 500",
    formatar_pct(cancel["taxa_caro"], 0),
    f"até R$ 150: {formatar_pct(cancel['taxa_barato'], 0)}",
    delta_color="off",
    delta_arrow="off",
    border=True,
)
faixas = consultar("SELECT * FROM analise.cancelamento_por_faixa")
rotulos_faixa = [f.split(". ", 1)[1] for f in faixas.faixa_orcamento]
mostrar(
    barras_horizontais(
        rotulos_faixa,
        (faixas.taxa_cancelamento * 100).tolist(),
        "OS canceladas",
        formato="%{x:.1f}%",
        textos=[formatar_pct(v) for v in faixas.taxa_cancelamento],
    ),
    faixas.assign(
        Orçamento=rotulos_faixa,
        OS=faixas.qtd_os.map(formatar_numero),
        Canceladas=faixas.qtd_canceladas,
        **{
            "% canceladas": faixas.taxa_cancelamento.map(formatar_pct),
            "Valor perdido": faixas.valor_perdido.map(formatar_moeda),
        },
    )[["Orçamento", "OS", "Canceladas", "% canceladas", "Valor perdido"]],
)
st.caption(
    "Quanto mais caro o orçamento, mais o cliente desiste. Parcelar no cartão, dividir o serviço "
    "em etapas (o urgente agora, o resto no mês seguinte) ou mostrar a peça gasta ajuda a "
    "segurar essas vendas."
)

# ---- Mecânicos ----
secao("Produção por mecânico")
mecanicos = (
    os_.groupby("mecanico", as_index=False)
    .agg(
        qtd=("numero_os", "count"),
        mao=("valor_mao_obra", "sum"),
        dias=("dias_na_oficina", "mean"),
        inicio=("data_abertura", "min"),
    )
    .sort_values("mao", ascending=False)
)
mostrar(
    barras_horizontais(
        mecanicos.mecanico.tolist(),
        mecanicos.mao.tolist(),
        "Mão de obra",
        textos=[formatar_moeda_curta(v) for v in mecanicos.mao],
    ),
    mecanicos.assign(
        Mecânico=mecanicos.mecanico,
        OS=mecanicos.qtd,
        **{
            "Mão de obra": mecanicos.mao.map(formatar_moeda),
            "Dias médios": mecanicos.dias.map(lambda d: formatar_numero(d, 1)),
            "Primeira OS no período": mecanicos.inicio.map(formatar_mes),
        },
    )[["Mecânico", "OS", "Mão de obra", "Dias médios", "Primeira OS no período"]],
)
st.caption(
    "Atenção ao comparar: um mecânico contratado no meio do período tem menos meses de "
    "produção (veja a coluna 'Primeira OS no período' na tabela)."
)

# ---- Prazo por mecânico (sempre 12 meses) ----
secao(
    "Prazo de entrega por mecânico",
    "Últimos 12 meses, sem a troca de óleo (rápida para todo mundo).",
)
prazo = consultar("SELECT * FROM analise.oficina_prazo ORDER BY dias_medios DESC")
mais_lento = prazo.iloc[0]
mostrar(
    barras_horizontais(
        prazo.mecanico.tolist(),
        prazo.dias_medios.tolist(),
        "Dias médios",
        formato="%{x:.1f} dias",
        textos=[f"{formatar_numero(d, 1)} dias" for d in prazo.dias_medios],
        cores=[SERIES[1] if i == 0 else NEUTRO for i in range(len(prazo))],
    ),
    prazo.assign(
        Mecânico=prazo.mecanico,
        OS=prazo.qtd_os,
        **{
            "Dias médios": prazo.dias_medios.map(lambda d: formatar_numero(d, 1)),
            "Entregue no dia": prazo.entregue_no_dia_pct.map(formatar_pct),
            "3 dias ou mais": prazo.tres_dias_ou_mais_pct.map(formatar_pct),
        },
    )[["Mecânico", "OS", "Dias médios", "Entregue no dia", "3 dias ou mais"]],
)
st.caption(
    f"Em laranja, o mais lento: {mais_lento.mecanico} entrega "
    f"{formatar_pct(mais_lento.entregue_no_dia_pct, 0)} das OS no mesmo dia, contra "
    f"{formatar_pct(prazo.iloc[1:].entregue_no_dia_pct.mean(), 0)} dos colegas. Moto parada é "
    "cliente sem trabalhar (principalmente motoboy): vale acompanhar ou parear com um mecânico "
    "mais experiente."
)

# ---- Serviços ----
secao("Serviços")
servicos = (
    os_.groupby("servico", as_index=False)
    .agg(
        qtd=("numero_os", "count"),
        ticket=("valor_total", "mean"),
        mao=("valor_mao_obra", "mean"),
        pecas=("valor_pecas", "mean"),
        total=("valor_total", "sum"),
    )
    .sort_values("total", ascending=False)
)
mostrar(
    barras_horizontais(
        servicos.servico.tolist(),
        servicos.total.tolist(),
        "Faturamento",
        textos=[formatar_moeda_curta(v) for v in servicos.total],
    ),
    servicos.assign(
        Serviço=servicos.servico,
        OS=servicos.qtd,
        **{
            "Ticket médio": servicos.ticket.map(formatar_moeda),
            "Mão de obra média": servicos.mao.map(formatar_moeda),
            "Peças em média": servicos.pecas.map(formatar_moeda),
        },
    )[["Serviço", "OS", "Ticket médio", "Mão de obra média", "Peças em média"]],
)
oleo = servicos[servicos.servico == "Troca de óleo"]
if not oleo.empty:
    st.caption(
        f"A troca de óleo é o serviço mais frequente ({formatar_numero(oleo.qtd.iloc[0])} OS), "
        "mas com ticket baixo: é a porta de entrada para oferecer revisão, relação e pneus."
    )

# ---- Venda casada (sempre 12 meses) ----
secao(
    "Venda casada: o que oferecer junto com cada serviço",
    "Últimos 12 meses. Potencial = se 60% das OS levassem o item (meta usada como premissa).",
)
casada = consultar("SELECT * FROM analise.oficina_venda_casada")
st.metric(
    "Receita extra possível por ano",
    formatar_moeda_curta(casada.receita_potencial_12m.sum()),
    f"{formatar_moeda_curta(casada.margem_potencial_12m.sum())} de margem",
    delta_color="off",
    delta_arrow="off",
    border=True,
)
st.dataframe(
    casada.assign(
        **{
            "Serviço + item": casada.servico + " + " + casada.item.str.lower(),
            "Levaram o item": (casada.taxa_atual * 100).round(),
            "Receita extra": casada.receita_potencial_12m.map(formatar_moeda_curta),
            "OS no período": casada.qtd_os.map(formatar_numero),
        },
    )[["Serviço + item", "Levaram o item", "Receita extra", "OS no período"]],
    hide_index=True,
    column_config={
        "Levaram o item": st.column_config.ProgressColumn(
            "Levaram o item", min_value=0, max_value=100, format="%.0f%%", width="small"
        ),
    },
)
st.caption(
    'Um lembrete no balcão ("trocou o óleo? e o filtro?") ou um kit com preço fechado '
    "resolve a maior parte disso sem desconto."
)
