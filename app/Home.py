"""Ponto de entrada do dashboard: configura a página e monta o menu de navegação.

Rodar com: uv run streamlit run app/Home.py

Cada página fica em app/paginas/. O `st.navigation` substitui a pasta `pages/` automática e
deixa escolher título, ícone e ordem do menu (como um roteador num app web em Java).
"""

import streamlit as st

from componentes import PAGINAS

st.set_page_config(
    page_title="Motopeças Analytics",
    page_icon=":material/two_wheeler:",
    layout="centered",
)

paginas = [
    st.Page(caminho, title=titulo, icon=icone, default=chave == "visao_geral")
    for chave, (caminho, titulo, icone) in PAGINAS.items()
]
st.navigation(paginas, position="top").run()
