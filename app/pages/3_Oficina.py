"""Oficina: volume de OS, produção por mecânico e desempenho dos serviços."""

import streamlit as st

from dados import consultar
from formatacao import formatar_mes, formatar_moeda, formatar_moeda_curta, formatar_numero
from graficos import barras_horizontais, linha, mostrar

st.set_page_config(page_title="Oficina · Motopeças", page_icon="🔧", layout="centered")
st.title("Oficina")

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
st.subheader("OS concluídas por mês")
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
st.caption("Só meses completos.")

# ---- Mecânicos ----
st.subheader("Produção por mecânico")
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

# ---- Serviços ----
st.subheader("Serviços")
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
