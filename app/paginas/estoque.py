"""Estoque: dinheiro parado, itens em falta, o que repor e a curva ABC."""

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
)
from graficos import SERIES, aplicar_layout, barras_agrupadas, barras_horizontais, mostrar

cabecalho("Estoque", "Dinheiro parado, itens em falta, o que comprar e a curva ABC.")

estoque_todo = consultar("SELECT * FROM analise.estoque")

# ---- Filtro (um só, no topo, vale para a página inteira) ----
categorias = ["Todas", *sorted(estoque_todo.categoria.unique())]
categoria = st.pills("Categoria", categorias, default="Todas") or "Todas"
estoque = (
    estoque_todo if categoria == "Todas" else estoque_todo[estoque_todo.categoria == categoria]
)

sem_giro = estoque[estoque.situacao == "Sem giro"]
em_falta = estoque[estoque.situacao == "Em falta"]
repor = estoque[estoque.situacao == "Repor"]

col1, col2 = st.columns(2)
col1.metric(
    "Valor em estoque",
    formatar_moeda_curta(estoque.valor_estoque.sum()),
    border=True,
    help="Quantidade em estoque x custo de cada item.",
)
col2.metric(
    "Parado há 6+ meses",
    formatar_moeda_curta(sem_giro.valor_estoque.sum()),
    f"{len(sem_giro)} itens",
    delta_color="off",
    delta_arrow="off",  # é só uma contagem, não uma alta
    border=True,
    help="Itens com estoque que não vendem há 180 dias ou mais.",
)
col1, col2 = st.columns(2)
col1.metric(
    "Em falta",
    f"{len(em_falta)} itens",
    f"{(em_falta.classe_abc == 'A').sum()} da curva A",
    delta_color="off",
    delta_arrow="off",
    border=True,
    help="Estoque zerado, mas o item vendeu nos últimos 90 dias.",
)
col2.metric(
    "Abaixo do mínimo",
    f"{len(repor)} itens",
    border=True,
    help="Estoque abaixo do mínimo cadastrado e com saída recente.",
)

# ---- Dinheiro parado por categoria ----
secao("Onde está o dinheiro parado")
por_categoria = (
    sem_giro.groupby("categoria", as_index=False)
    .agg(valor=("valor_estoque", "sum"), itens=("sku", "count"))
    .sort_values("valor", ascending=False)
)
if por_categoria.empty:
    st.info("Nenhum item sem giro nesta categoria.")
else:
    fig = barras_horizontais(
        por_categoria.categoria.tolist(),
        por_categoria.valor.tolist(),
        "Valor parado",
        textos=[formatar_moeda_curta(v) for v in por_categoria.valor],
    )
    mostrar(
        fig,
        por_categoria.assign(
            Categoria=por_categoria.categoria,
            Itens=por_categoria.itens,
            **{"Valor parado": por_categoria.valor.map(formatar_moeda)},
        )[["Categoria", "Itens", "Valor parado"]],
    )

    st.markdown("**Itens sem giro, do maior valor parado para o menor**")
    lista = sem_giro.sort_values("valor_estoque", ascending=False)
    st.dataframe(
        lista.assign(
            Item=lista.descricao,
            Estoque=lista.estoque_atual,
            **{
                "Valor parado": lista.valor_estoque.map(formatar_moeda),
                "Dias sem vender": lista.dias_sem_venda.map(formatar_numero),
                "Última venda": lista.ultima_saida.map(
                    lambda d: formatar_data(d) or "nunca vendeu"
                ),
            },
        )[["Item", "Valor parado", "Dias sem vender", "Estoque", "Última venda"]],
        hide_index=True,
    )
    st.caption("Sugestão: promoção, kit com itens que giram ou devolução ao fornecedor.")

# ---- Estoque x motos atendidas (loja toda) ----
secao(
    "Estoque × motos que a oficina atende",
    "Peças específicas de cada moto (loja toda). Barras desiguais = compra fora do perfil.",
)
motos = consultar("SELECT * FROM analise.estoque_por_moto")
rotulos_moto = [m.split(" ", 1)[1] for m in motos.moto]
mostrar(
    barras_agrupadas(
        rotulos_moto,
        {
            "% das OS (12 meses)": (motos.participacao_os * 100).tolist(),
            "% do estoque parado": (motos.participacao_parado * 100).tolist(),
        },
    ),
    motos.assign(
        Moto=motos.moto,
        **{
            "% das OS": motos.participacao_os.map(formatar_pct),
            "% do estoque parado": motos.participacao_parado.map(formatar_pct),
            "Valor parado": motos.valor_parado.map(formatar_moeda),
            "Parado / estoque da moto": motos.parado_pct.map(formatar_pct),
        },
    )[["Moto", "% das OS", "% do estoque parado", "Valor parado", "Parado / estoque da moto"]],
)
raras = motos.nsmallest(2, "participacao_os")
st.caption(
    f"{' e '.join(m.split(' ', 1)[1] for m in raras.moto)} somam "
    f"{formatar_pct(raras.participacao_os.sum(), 0)} das OS, mas "
    f"{formatar_pct(raras.participacao_parado.sum(), 0)} do estoque parado. Para motos que "
    "aparecem pouco, vale manter só o básico e comprar o resto sob encomenda."
)

# ---- O que comprar ----
secao("O que comprar agora")
comprar = estoque[estoque.situacao.isin(["Em falta", "Repor"])].sort_values(
    ["classe_abc", "receita_12m"], ascending=[True, False]
)
if comprar.empty:
    st.success("Nenhum item em falta ou abaixo do mínimo nesta categoria.")
else:
    st.dataframe(
        comprar.assign(
            Item=comprar.descricao,
            Curva=comprar.classe_abc,
            Situação=comprar.situacao,
            Estoque=comprar.estoque_atual,
            Mínimo=comprar.estoque_minimo,
            **{
                "Vendidos em 90 dias": comprar.qtd_vendida_90d,
                "Receita 12 meses": comprar.receita_12m.map(formatar_moeda),
            },
        )[
            [
                "Item",
                "Situação",
                "Curva",
                "Estoque",
                "Mínimo",
                "Vendidos em 90 dias",
                "Receita 12 meses",
            ]
        ],
        hide_index=True,
    )
    st.caption("Ordenado pela curva ABC: itens A primeiro, porque são os que mais faturam.")

# ---- Curva ABC (sempre da loja toda) ----
secao("Curva ABC", "Sempre da loja toda, independentemente do filtro.")
abc = estoque_todo.sort_values("receita_12m", ascending=False).reset_index(drop=True)
abc["pct_itens"] = (abc.index + 1) / len(abc) * 100
abc["pct_receita"] = abc.receita_12m.cumsum() / abc.receita_12m.sum() * 100
qtd_a = (abc.classe_abc == "A").sum()
pct_a = qtd_a / len(abc) * 100
st.write(
    f"**{qtd_a} itens ({formatar_numero(pct_a)}% do catálogo) fazem 80% da receita** dos "
    "últimos 12 meses. São esses que nunca podem faltar na prateleira."
)
fig = go.Figure()
fig.add_scatter(
    x=abc.pct_itens,
    y=abc.pct_receita,
    mode="lines",
    name="Receita acumulada",
    line={"color": SERIES[0], "width": 2},
    hovertemplate="%{x:.0f}% dos itens fazem %{y:.0f}% da receita<extra></extra>",
)
fig.add_scatter(
    x=[pct_a],
    y=[80],
    mode="markers",
    marker={"size": 10, "color": SERIES[0]},
    hoverinfo="skip",
    showlegend=False,
)
fig.add_annotation(
    x=pct_a,
    y=80,
    text=f"curva A: {formatar_numero(pct_a)}% dos itens",
    showarrow=False,
    xanchor="left",
    xshift=10,
)
fig.update_xaxes(ticksuffix="%", range=[0, 100])
fig.update_yaxes(ticksuffix="%", range=[0, 105])
fig = aplicar_layout(fig, legenda=False)
resumo_abc = estoque_todo.groupby("classe_abc", as_index=False).agg(
    itens=("sku", "count"), receita=("receita_12m", "sum")
)
mostrar(
    fig,
    resumo_abc.assign(
        Classe=resumo_abc.classe_abc,
        Itens=resumo_abc.itens,
        **{"Receita 12 meses": resumo_abc.receita.map(formatar_moeda)},
    )[["Classe", "Itens", "Receita 12 meses"]],
)
st.caption("Eixo horizontal: % dos itens do catálogo, do que mais vende para o que menos vende.")
