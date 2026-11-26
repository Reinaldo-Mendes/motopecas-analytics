"""Ponto de entrada do dashboard: configura a página e monta o menu de navegação.

Rodar com: uv run streamlit run app/Home.py

Cada página fica em app/paginas/. O `st.navigation` substitui a pasta `pages/` automática e
deixa escolher título, ícone e ordem do menu (como um roteador num app web em Java).
"""

import sys
from pathlib import Path

import streamlit as st

# Depois de um push, o Streamlit Cloud atualiza os arquivos mas mantém o processo Python: módulos
# já importados (src/, app/) ficariam na versão antiga e quebrariam com o código novo
# (ImportError). Este script roda a cada interação, então descartamos aqui os módulos do próprio
# projeto para que sejam lidos de novo do disco. São pequenos (milissegundos) e os caches do
# Streamlit continuam valendo, porque são guardados fora dos módulos.
PASTAS_DO_PROJETO = {
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parent.parent / "src",
}
for nome, modulo in list(sys.modules.items()):
    arquivo = getattr(modulo, "__file__", None)
    if (
        not nome.startswith("__")
        and arquivo
        and Path(arquivo).resolve().parent in PASTAS_DO_PROJETO
    ):
        del sys.modules[nome]

from componentes import PAGINAS  # noqa: E402

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
