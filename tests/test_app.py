"""Smoke test do dashboard: cada página precisa rodar sem erro com o banco real.

AppTest executa o app do Streamlit sem navegador (como um teste de integração). O teste abre o
ponto de entrada (Home.py, que monta o menu) e navega para cada página, como um usuário faria.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PASTA_APP = Path(__file__).resolve().parent.parent / "app"
TITULOS = {
    "visao_geral.py": "Motopeças",
    "estoque.py": "Estoque",
    "vendas.py": "Vendas e margem",
    "oficina.py": "Oficina",
    "clientes.py": "Clientes",
}


def test_todas_as_paginas_estao_no_teste():
    assert set(TITULOS) == {p.name for p in (PASTA_APP / "paginas").glob("*.py")}


@pytest.mark.parametrize(("pagina", "titulo"), TITULOS.items())
def test_pagina_roda_sem_erro(pagina, titulo):
    app = AppTest.from_file(str(PASTA_APP / "Home.py"), default_timeout=60).run()
    app.switch_page(f"paginas/{pagina}").run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.title[0].value == titulo  # confirma que trocou mesmo de página
    assert app.metric, "a página deveria mostrar KPIs"


def test_visao_geral_e_a_pagina_inicial():
    app = AppTest.from_file(str(PASTA_APP / "Home.py"), default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.title[0].value == "Motopeças"
