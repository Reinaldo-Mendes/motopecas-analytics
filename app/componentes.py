"""Peças de interface reutilizadas pelas páginas: menu, cabeçalho e cartões de achados."""

from __future__ import annotations

import streamlit as st

from dados import RAIZ  # noqa: F401  (garante src/ no caminho de importação)
from diagnostico import Achado

# chave -> (arquivo, título no menu, ícone). Os ícones são do Material Symbols, do Google.
PAGINAS: dict[str, tuple[str, str, str]] = {
    "visao_geral": ("paginas/visao_geral.py", "Visão geral", ":material/space_dashboard:"),
    "estoque": ("paginas/estoque.py", "Estoque", ":material/inventory_2:"),
    "vendas": ("paginas/vendas.py", "Vendas e margem", ":material/payments:"),
    "oficina": ("paginas/oficina.py", "Oficina", ":material/build:"),
    "clientes": ("paginas/clientes.py", "Clientes", ":material/group:"),
    "dados_brutos": ("paginas/dados_brutos.py", "Dados brutos", ":material/table_view:"),
}

# tipo do achado -> (rótulo, ícone, cor do selo). Cor nunca vem sozinha: sempre com rótulo.
TIPOS_ACHADO = {
    "alerta": ("Atenção", ":material/warning:", "orange"),
    "oportunidade": ("Oportunidade", ":material/trending_up:", "green"),
    "info": ("Contexto", ":material/info:", "blue"),
}


def cabecalho(titulo: str, subtitulo: str | None = None) -> None:
    """Título da página com uma linha de contexto logo abaixo."""
    st.title(titulo, anchor=False)
    if subtitulo:
        st.caption(subtitulo)


def secao(titulo: str, subtitulo: str | None = None) -> None:
    """Título de seção (sem a âncora de link que o Streamlit põe nos títulos)."""
    st.subheader(titulo, anchor=False)
    if subtitulo:
        st.caption(subtitulo)


def link_pagina(chave: str, rotulo: str, icone: str | None = None) -> None:
    """Link para outra página do menu."""
    caminho, _, icone_pagina = PAGINAS[chave]
    st.page_link(caminho, label=rotulo, icon=icone or icone_pagina)


def cartao_achado(achado: Achado, com_link: bool = True) -> None:
    """Cartão com selo do tipo, o número em destaque, a explicação e o link para o detalhe."""
    rotulo, icone, cor = TIPOS_ACHADO[achado.tipo]
    with st.container(border=True):
        st.badge(f"{rotulo} · {achado.tema}", icon=icone, color=cor)
        st.markdown(f"### {achado.valor}")
        st.markdown(achado.texto)
        if com_link:
            link_pagina(achado.pagina, "Ver detalhes", ":material/arrow_forward:")


def grade_de_cartoes(achados: list[Achado], com_link: bool = True) -> None:
    """Cartões em duas colunas (no celular, o Streamlit empilha numa coluna só)."""
    for i in range(0, len(achados), 2):
        colunas = st.columns(2)
        for coluna, achado in zip(colunas, achados[i : i + 2], strict=False):
            with coluna:
                cartao_achado(achado, com_link)
