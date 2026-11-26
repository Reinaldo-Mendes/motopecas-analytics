"""Vendas e margem: evolução mensal, margem por categoria e sazonalidade."""

import streamlit as st

from dados import consultar
from formatacao import MESES_ABREV, formatar_mes, formatar_moeda, formatar_moeda_curta, formatar_pct
from graficos import NEUTRO, SERIES, barras_empilhadas, barras_horizontais, linha, mostrar

st.set_page_config(page_title="Vendas e Margem · Motopeças", page_icon="💰", layout="centered")
st.title("Vendas e margem")

periodo = (
    st.segmented_control(
        "Período", ["Últimos 12 meses", "Últimos 24 meses"], default="Últimos 12 meses"
    )
    or "Últimos 12 meses"
)
dias = 365 if periodo == "Últimos 12 meses" else 730
filtro_data = f"data > (SELECT data_referencia FROM analise.referencia) - {dias}"

fat = consultar(f"""
    SELECT * FROM analise.faturamento_mensal
    WHERE mes > (SELECT date_trunc('month', data_referencia) FROM analise.referencia)
                - INTERVAL {dias // 30} MONTH
    ORDER BY mes
""")
itens = consultar(f"SELECT * FROM analise.itens_vendidos WHERE {filtro_data}")
pedidos = consultar(f"""
    SELECT count(DISTINCT numero_pedido) AS qtd, sum(quantidade * preco_unitario) AS receita
    FROM limpo.vendas WHERE {filtro_data}
""").iloc[0]
mao = (
    consultar(f"""SELECT sum(valor_mao_obra) AS v FROM analise.ordens_concluidas
                    WHERE data_abertura > (SELECT data_referencia FROM analise.referencia) - {dias}
                 """)
    .iloc[0]
    .v
)

receita_pecas = itens.receita.sum()
custo = itens.custo_total.sum()
col1, col2 = st.columns(2)
col1.metric(
    "Faturamento",
    formatar_moeda_curta(receita_pecas + mao),
    border=True,
    help="Peças (balcão + oficina) + mão de obra.",
)
col2.metric(
    "Lucro bruto",
    formatar_moeda_curta(receita_pecas + mao - custo),
    border=True,
    help="Faturamento menos o custo das peças.",
)
col1, col2 = st.columns(2)
col1.metric(
    "Margem das peças",
    formatar_pct((receita_pecas - custo) / receita_pecas),
    border=True,
    help="(Preço de venda - custo) / preço de venda.",
)
col2.metric(
    "Ticket médio no balcão",
    formatar_moeda(pedidos.receita / pedidos.qtd),
    border=True,
    help="Valor médio de cada pedido de balcão.",
)

# ---- Evolução ----
st.subheader("Faturamento por mês")
rotulos = [formatar_mes(m) for m in fat.mes]
mostrar(
    barras_empilhadas(
        rotulos,
        {
            "Peças no balcão": fat.pecas_balcao.tolist(),
            "Peças na oficina": fat.pecas_oficina.tolist(),
            "Mão de obra": fat.mao_de_obra.tolist(),
        },
        completos=fat.mes_completo.tolist(),
    ),
    fat.assign(
        Mês=rotulos,
        Faturamento=fat.faturamento.map(formatar_moeda),
        **{"Lucro bruto": fat.lucro_bruto.map(formatar_moeda)},
    )[["Mês", "Faturamento", "Lucro bruto"]],
)
st.caption("Barras claras = mês incompleto.")

st.subheader("Margem das peças por mês")
completos = fat[fat.mes_completo]
margens = completos.margem_pecas_pct * 100
fig = linha(
    [formatar_mes(m) for m in completos.mes],
    margens.tolist(),
    "Margem",
    formato_y=",.0f",
    sufixo="%",
    rotulo_final=formatar_pct(completos.margem_pecas_pct.iloc[-1]),
)
# Folga de 2 p.p. (pontos percentuais) em volta: um eixo justo demais faz 1 p.p. parecer queda
fig.update_yaxes(range=[margens.min() - 2, margens.max() + 2], dtick=1)
mostrar(
    fig,
    completos.assign(
        Mês=[formatar_mes(m) for m in completos.mes],
        Margem=completos.margem_pecas_pct.map(formatar_pct),
    )[["Mês", "Margem"]],
)

# ---- Margem por categoria ----
st.subheader("Margem por categoria")
categorias = itens.groupby("categoria", as_index=False).agg(
    receita=("receita", "sum"), custo=("custo_total", "sum")
)
categorias["margem_pct"] = (categorias.receita - categorias.custo) / categorias.receita
categorias["participacao"] = categorias.receita / categorias.receita.sum()
categorias = categorias.sort_values("margem_pct", ascending=False)
mostrar(
    barras_horizontais(
        categorias.categoria.tolist(),
        (categorias.margem_pct * 100).tolist(),
        "Margem",
        formato="%{x:,.1f}%",
        textos=[formatar_pct(m) for m in categorias.margem_pct],
    ),
    categorias.assign(
        Categoria=categorias.categoria,
        Receita=categorias.receita.map(formatar_moeda),
        Margem=categorias.margem_pct.map(formatar_pct),
        **{"% da receita": categorias.participacao.map(formatar_pct)},
    )[["Categoria", "Receita", "% da receita", "Margem"]],
)
maior = categorias.sort_values("receita", ascending=False).iloc[0]
st.caption(
    f"{maior.categoria} responde por {formatar_pct(maior.participacao, 0)} da receita com margem "
    f"de {formatar_pct(maior.margem_pct, 0)}. Revisar preço ou fornecedor dessa categoria "
    "mexe mais no lucro do que qualquer outra."
)

# ---- Sazonalidade ----
st.subheader("Pneus: efeito da época de chuva")
pneus = consultar("""
    SELECT month(data) AS mes, sum(receita) / count(DISTINCT date_trunc('month', data)) AS media
    FROM analise.itens_vendidos
    WHERE categoria = 'Pneus e câmaras'
    GROUP BY 1 ORDER BY 1
""")
chuva = pneus.mes.isin([11, 12, 1, 2, 3])
fig = barras_horizontais(
    [MESES_ABREV[m - 1] for m in pneus.mes],
    pneus.media.tolist(),
    "Média mensal",
    textos=[formatar_moeda_curta(v) for v in pneus.media],
    cores=[SERIES[0] if c else NEUTRO for c in chuva],
)
mostrar(
    fig,
    pneus.assign(
        Mês=[MESES_ABREV[m - 1] for m in pneus.mes],
        Época=chuva.map({True: "Chuva", False: "Seca"}),
        **{"Receita média": pneus.media.map(formatar_moeda)},
    )[["Mês", "Época", "Receita média"]],
)
fator = pneus.media[chuva].mean() / pneus.media[~chuva].mean() - 1
st.caption(
    f"Em azul, a época de chuva (nov a mar): a venda de pneus sobe {formatar_pct(fator, 0)} em "
    "relação à seca. Vale reforçar o estoque de pneus a partir de outubro."
)
