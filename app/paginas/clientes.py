"""Clientes: troca de óleo prevista, perfil descoberto pela frequência, quem sumiu e quem compra."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from componentes import cabecalho, secao
from dados import consultar
from formatacao import (
    formatar_data,
    formatar_moeda,
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
    formatar_telefone,
)
from graficos import STATUS, aplicar_layout, eixo_de_categorias, mostrar

cabecalho(
    "Clientes",
    "O sistema da loja não registra se o cliente é motoboy: o perfil foi descoberto pela "
    "frequência de visitas (a cada ~30 dias = motoboy; empresa ou 3+ motos = frota).",
)

clientes = consultar("SELECT * FROM analise.clientes_perfil WHERE perfil <> 'Sem compras'")
ordem_perfis = ["Motoboy", "Uso pessoal", "Frota"]

perfil = st.segmented_control("Perfil", ["Todos", *ordem_perfis], default="Todos") or "Todos"
filtrados = clientes if perfil == "Todos" else clientes[clientes.perfil == perfil]

sumidos = filtrados[
    filtrados.status.isin(["Em risco", "Inativo"]) & (filtrados.dias_desde_ultima_visita <= 365)
]
col1, col2 = st.columns(2)
col1.metric(
    "Clientes ativos",
    formatar_numero((filtrados.status == "Ativo").sum()),
    border=True,
    help="Voltaram dentro do intervalo habitual deles.",
)
col2.metric("Gasto médio em 12 meses", formatar_moeda(filtrados.gasto_12m.mean()), border=True)
col1, col2 = st.columns(2)
col1.metric(
    "Sumiram no último ano",
    formatar_numero(len(sumidos)),
    border=True,
    help="Status 'em risco' ou 'inativo', com última visita há menos de 1 ano.",
)
col2.metric(
    "Gasto desses clientes",
    formatar_moeda_curta(sumidos.gasto_12m.sum()),
    border=True,
    help="Quanto os clientes que sumiram gastaram nos últimos 12 meses.",
)

# ---- Troca de óleo prevista ----
secao(
    "Troca de óleo prevista para esta semana",
    "Pelo ritmo de cada cliente (mediana entre as trocas, com 3+ trocas no histórico). "
    "Mandar uma mensagem antes que ele troque o óleo em outro lugar.",
)
oleo = consultar("""
    SELECT * FROM analise.clientes_troca_oleo
    WHERE situacao IN ('Esta semana', 'Atrasada')
    ORDER BY gasto_12m DESC
""")
oleo = oleo if perfil == "Todos" else oleo[oleo.perfil == perfil]
ticket_troca = consultar(
    "SELECT avg(valor_total) AS v FROM analise.ordens_concluidas WHERE servico = 'Troca de óleo'"
).v.iloc[0]
col1, col2 = st.columns(2)
col1.metric(
    "Clientes para chamar",
    formatar_numero(len(oleo)),
    f"{(oleo.situacao == 'Atrasada').sum()} já atrasados",
    delta_color="off",
    delta_arrow="off",
    border=True,
)
col2.metric(
    "Receita em jogo",
    formatar_moeda_curta(len(oleo) * ticket_troca),
    border=True,
    help="Clientes da lista x ticket médio de uma OS de troca de óleo.",
)
if oleo.empty:
    st.success("Ninguém com troca prevista neste perfil.")
else:
    st.dataframe(
        oleo.assign(
            Cliente=oleo.nome,
            Telefone=oleo.telefone.map(formatar_telefone),
            Perfil=oleo.perfil,
            Moto=oleo.moto_principal.fillna("—"),
            Situação=oleo.situacao,
            **{
                "Última troca": oleo.ultima_troca.map(formatar_data),
                "Previsão": oleo.proxima_troca.map(formatar_data),
                "Troca a cada": oleo.intervalo_dias.map(lambda d: f"{d} dias"),
            },
        )[
            [
                "Cliente",
                "Telefone",
                "Situação",
                "Previsão",
                "Última troca",
                "Troca a cada",
                "Perfil",
                "Moto",
            ]
        ],
        hide_index=True,
    )

# ---- Perfil x status ----
secao("Status dos clientes em cada perfil")
contagem = (
    clientes.groupby(["perfil", "status"])
    .size()
    .unstack(fill_value=0)
    .reindex(index=ordem_perfis, columns=list(STATUS), fill_value=0)
)
fig = go.Figure()
for status, cor in STATUS.items():
    fig.add_bar(
        y=contagem.index,
        x=contagem[status],
        name=status,
        orientation="h",
        marker={"color": cor},
        customdata=contagem[status],
        hovertemplate=(
            f"<b>%{{y}}</b><br>{status}: %{{customdata}} clientes (%{{x:.0f}}%)<extra></extra>"
        ),
    )
# barnorm="percent": cada perfil vira 100%, assim a frota (poucos clientes) também aparece
fig.update_layout(barmode="stack", barnorm="percent", bargap=0.35)
fig = eixo_de_categorias(aplicar_layout(fig, altura=240))
fig.update_xaxes(ticksuffix="%", range=[0, 100], dtick=25, tickangle=0)
tabela = contagem.reset_index().rename(columns={"perfil": "Perfil"})
tabela["Total"] = contagem.sum(axis=1).to_numpy()
gasto = clientes.groupby("perfil").gasto_12m.sum().reindex(ordem_perfis)
tabela["% do gasto 12m"] = (gasto / gasto.sum()).map(formatar_pct).to_numpy()
mostrar(fig, tabela)

motoboys = clientes[clientes.perfil == "Motoboy"]
st.caption(
    f"Motoboys são {formatar_pct(len(motoboys) / len(clientes), 0)} dos clientes, mas fazem "
    f"{formatar_pct(motoboys.gasto_12m.sum() / clientes.gasto_12m.sum(), 0)} do gasto dos "
    "clientes cadastrados nos últimos 12 meses."
)

# ---- Lista de retorno ----
secao(
    "Para ligar: clientes que começaram a sumir",
    "Pararam de vir no último ano, dos que mais gastavam para os que menos.",
)
lista = sumidos.sort_values("gasto_12m", ascending=False)
if lista.empty:
    st.success("Nenhum cliente sumido neste perfil.")
else:
    st.dataframe(
        lista.assign(
            Cliente=lista.nome,
            Perfil=lista.perfil,
            Status=lista.status,
            Telefone=lista.telefone.map(formatar_telefone),
            Moto=lista.moto_principal.fillna("—"),
            **{
                "Última visita": lista.ultima_visita.map(formatar_data),
                "Gasto 12 meses": lista.gasto_12m.map(formatar_moeda),
            },
        )[["Cliente", "Telefone", "Gasto 12 meses", "Perfil", "Status", "Última visita", "Moto"]],
        hide_index=True,
    )
    st.caption("Nomes e telefones fictícios.")

# ---- Melhores clientes ----
secao("Quem mais comprou nos últimos 12 meses")
top = filtrados.sort_values("gasto_12m", ascending=False).head(10)
st.dataframe(
    top.assign(
        Cliente=top.nome,
        Perfil=top.perfil,
        Visitas=top.qtd_visitas,
        **{
            "Gasto 12 meses": top.gasto_12m.map(formatar_moeda),
            "Vem a cada": top.intervalo_medio_dias.map(
                lambda d: "—" if pd.isna(d) else f"{formatar_numero(d)} dias"
            ),
        },
    )[["Cliente", "Gasto 12 meses", "Perfil", "Visitas", "Vem a cada"]],
    hide_index=True,
)
