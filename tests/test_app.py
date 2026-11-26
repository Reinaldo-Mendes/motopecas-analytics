"""Smoke test do dashboard: cada página precisa rodar sem erro com o banco real.

AppTest executa a página do Streamlit sem navegador (como um teste de integração).
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PASTA_APP = Path(__file__).resolve().parent.parent / "app"
PAGINAS = ["Home.py", *sorted(p.name for p in (PASTA_APP / "pages").glob("*.py"))]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_roda_sem_erro(pagina):
    caminho = PASTA_APP / pagina if pagina == "Home.py" else PASTA_APP / "pages" / pagina
    app = AppTest.from_file(str(caminho), default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.metric, "a página deveria mostrar KPIs"
