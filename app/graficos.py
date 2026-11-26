"""Gráficos Plotly no padrão visual do projeto.

Regras seguidas em todos os gráficos:
- texto, grade e fundo vêm do tema do Streamlit (`theme="streamlit"`), que sabe se a página
  está clara ou escura; aqui só fixamos as cores das SÉRIES;
- as cores das séries (azul, laranja, verde-água, nessa ordem) foram validadas para daltonismo
  e contraste nos fundos claro E escuro, por isso uma paleta só serve para os dois;
- status (ativo/em risco/inativo) usa cores próprias, sempre com rótulo na legenda;
- um único eixo Y por gráfico (nada de eixo duplo);
- todo gráfico tem uma tabela "Ver tabela" logo abaixo (acessibilidade).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SERIES = ["#338ced", "#e76624", "#00a888"]  # ordem fixa: nunca reordenar nem gerar cores novas
NEUTRO = "#8c8c8c"  # para o "resto" quando um destaque é colorido
STATUS = {"Ativo": "#0aac23", "Em risco": "#fbb315", "Inativo": "#dc3c3d"}
FONTE = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'  # Inter vem do tema
CONFIG_PLOTLY = {"displayModeBar": False, "scrollZoom": False}


def aplicar_layout(fig: go.Figure, altura: int = 320, legenda: bool = True) -> go.Figure:
    """Layout comum: margens enxutas, separadores brasileiros, eixos discretos."""
    fig.update_layout(
        height=altura,
        separators=",.",  # decimal com vírgula, milhar com ponto
        font={"family": FONTE, "size": 13},
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        showlegend=legenda,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "x": 0,
            "title": None,
            "traceorder": "normal",  # mesma ordem em que as séries foram adicionadas
        },
        hoverlabel={"font": {"family": FONTE}},
        barcornerradius=4,
    )
    # meses na vertical: no celular, na diagonal eles se sobrepõem
    fig.update_xaxes(showgrid=False, title=None, fixedrange=True, automargin=True, tickangle=-90)
    fig.update_yaxes(
        zeroline=False,
        title=None,
        fixedrange=True,
        # rótulo do valor dentro do gráfico, acima da linha de grade: sobra largura no celular
        ticklabelposition="inside top",
        nticks=5,
    )
    return fig


def eixo_de_categorias(fig: go.Figure) -> go.Figure:
    """Eixo Y de categorias (barras horizontais): um rótulo por barra, maior em cima, sem grade."""
    fig.update_yaxes(
        autorange="reversed",
        showgrid=False,
        ticklabelposition="outside",
        automargin=True,  # abre espaço à esquerda para o nome das categorias
        tickmode="linear",  # força um rótulo por categoria (o padrão pula quando acha apertado)
        dtick=1,
        nticks=None,
    )
    return fig


def mostrar(fig: go.Figure, tabela: pd.DataFrame | None = None) -> None:
    """Exibe o gráfico com o tema do Streamlit e, logo abaixo, a mesma informação em tabela."""
    st.plotly_chart(fig, config=CONFIG_PLOTLY, theme="streamlit")
    if tabela is not None:
        with st.expander("Ver tabela"):
            st.dataframe(tabela, hide_index=True)


def barras_empilhadas(
    rotulos: list[str],
    series: dict[str, list[float]],
    completos: list[bool] | None = None,
    formato: str = "R$ %{y:,.0f}",
) -> go.Figure:
    """Barras empilhadas por mês; meses incompletos aparecem esmaecidos."""
    opacidade = [1.0 if c else 0.4 for c in completos] if completos else 1.0
    fig = go.Figure()
    for (nome, valores), cor in zip(series.items(), SERIES, strict=False):
        fig.add_bar(
            x=rotulos,
            y=valores,
            name=nome,
            marker={"color": cor, "opacity": opacidade, "line": {"width": 0}},
            hovertemplate=f"<b>%{{x}}</b><br>{nome}: {formato}<extra></extra>",
        )
    fig.update_layout(barmode="stack", bargap=0.25)
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return aplicar_layout(fig)


def linha(
    rotulos: list[str],
    valores: list[float],
    nome: str,
    formato_y: str = ",.0f",
    prefixo: str = "",
    sufixo: str = "",
    rotulo_final: str | None = None,
) -> go.Figure:
    """Linha única de 2px com marcadores, rotulando só o último ponto."""
    fig = go.Figure()
    fig.add_scatter(
        x=rotulos,
        y=valores,
        name=nome,
        mode="lines+markers",
        line={"color": SERIES[0], "width": 2},
        marker={"size": 8, "color": SERIES[0]},
        hovertemplate=(
            f"<b>%{{x}}</b><br>{nome}: {prefixo}%{{y:{formato_y}}}{sufixo}<extra></extra>"
        ),
    )
    if rotulo_final:
        fig.add_annotation(
            x=rotulos[-1], y=valores[-1], text=rotulo_final, showarrow=False, yshift=16
        )
    fig.update_yaxes(tickprefix=prefixo, ticksuffix=sufixo, tickformat=formato_y)
    return aplicar_layout(fig, legenda=False)


def barras_agrupadas(
    categorias: list[str],
    series: dict[str, list[float]],
    formato: str = "%{x:.0f}%",
    sufixo_texto: str = "%",
) -> go.Figure:
    """Barras horizontais lado a lado para comparar 2 ou 3 medidas na mesma escala.

    Cada barra leva o valor na ponta (rótulo direto) e a legenda fica no topo: a cor nunca é
    a única forma de saber qual série é qual.
    """
    fig = go.Figure()
    for (nome, valores), cor in zip(series.items(), SERIES, strict=False):
        fig.add_bar(
            y=categorias,
            x=valores,
            orientation="h",
            name=nome,
            marker={"color": cor},
            text=[f"{v:.0f}{sufixo_texto}" for v in valores],
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"<b>%{{y}}</b><br>{nome}: {formato}<extra></extra>",
        )
    fig.update_xaxes(showticklabels=False, showgrid=False, showline=False)
    altura = max(260, 34 * len(series) * len(categorias) + 60)
    fig = aplicar_layout(fig, altura=altura)
    fig.update_layout(
        barmode="group", bargap=0.25, bargroupgap=0.1, margin={"l": 8, "r": 48, "t": 8, "b": 8}
    )
    return eixo_de_categorias(fig)


def barras_horizontais(
    categorias: list[str],
    valores: list[float],
    nome: str,
    formato: str = "R$ %{x:,.0f}",
    textos: list[str] | None = None,
    cores: list[str] | None = None,
) -> go.Figure:
    """Barras horizontais de uma série só, maior em cima, com o valor na ponta da barra."""
    fig = go.Figure()
    fig.add_bar(
        y=categorias,
        x=valores,
        orientation="h",
        name=nome,
        marker={"color": cores or SERIES[0]},
        text=textos,
        textposition="outside",
        cliponaxis=False,
        hovertemplate=f"<b>%{{y}}</b><br>{nome}: {formato}<extra></extra>",
    )
    fig.update_xaxes(showticklabels=False, showgrid=False, showline=False)
    altura = max(220, 44 * len(categorias))
    fig = aplicar_layout(fig, altura=altura, legenda=False)
    fig.update_layout(margin={"l": 8, "r": 90, "t": 8, "b": 8}, bargap=0.3)
    return eixo_de_categorias(fig)
