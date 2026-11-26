"""Testes das views de métricas (src/sql/04 a 07).

Parte 1: um cenário pequeno, montado à mão, em que cada resultado esperado foi calculado
"na ponta do lápis" (ver comentários). Parte 2: conferência contra o gabarito do gerador.

Cenário (data de referência = 30/06/2026, a última data com movimento):

Produtos   custo  preço  estoque  mínimo  vendas
P-B          50    100      20       2    7 un. em 30/06/26 (balcão) + 1 un. na OS de 01/01/26
P-A          10     20       2       5    10 un. em 01/06/26
P-E          10     20       0       1    3 un. em 20/06/26
P-C           5     10      10       1    4 un. em 12/12/25 (200 dias antes da referência)
P-D          20     40       3       1    nunca vendeu (cadastro 01/01/25)

Clientes
1 João (PF)      7 OS de troca de óleo a cada 30 dias, de 01/01/26 a 30/06/26 -> motoboy ativo
2 Ana (PF)       3 compras no balcão (12/12/25, 01/06/26, 20/06/26) + 1 OS CANCELADA
3 Transp. (PJ)   1 compra no balcão (30/06/26)                          -> frota
4 Pedro (PF)     6 OS a cada 30 dias, de 03/08/25 a 31/12/25 -> motoboy que sumiu
"""

from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from conftest import valor
from pipeline import construir_banco

REFERENCIA = date(2026, 6, 30)


def data_br(d: date) -> str:
    """Data no formato que o ERP exporta."""
    return d.strftime("%d/%m/%Y")


def montar_csvs(pasta) -> None:
    """Escreve os 5 CSVs do cenário no mesmo formato 'sujo' do ERP."""
    produtos = pd.DataFrame(
        [
            ("P-B", "50,00", "100,00", 20, 2),
            ("P-A", "10,00", "20,00", 2, 5),
            ("P-E", "10,00", "20,00", 0, 1),
            ("P-C", "5,00", "10,00", 10, 1),
            ("P-D", "20,00", "40,00", 3, 1),
        ],
        columns=["sku", "custo", "preco_venda", "estoque_atual", "estoque_minimo"],
    )
    produtos = produtos.assign(
        descricao=produtos.sku,
        categoria="Teste",
        marca="X",
        compatibilidade="Universal",
        data_cadastro="2025-01-01",
    )
    clientes = pd.DataFrame(
        {
            "id_cliente": [1, 2, 3, 4],
            "nome": ["João Motoboy", "Ana Pessoal", "Transportes X Ltda", "Pedro Sumido"],
            "cpf_cnpj": [
                "111.111.111-11",
                "222.222.222-22",
                "33.333.333/0001-33",
                "444.444.444-44",
            ],
            "tipo_pessoa": ["PF", "PF", "PJ", "PF"],
            "telefone": ["35911111111", "35922222222", "35933333333", "35944444444"],
            "email": "",
            "cidade": "Serra Alta",
            "uf": "MG",
            "data_cadastro": "01/01/2025",
        }
    )
    vendas = pd.DataFrame(
        [
            (1, data_br(date(2026, 6, 30)), 3, "P-B", 7, "100,00"),
            (2, data_br(date(2026, 6, 1)), 2, "P-A", 10, "20,00"),
            (3, data_br(date(2026, 6, 20)), 2, "P-E", 3, "20,00"),
            (4, data_br(date(2025, 12, 12)), 2, "P-C", 4, "10,00"),
        ],
        columns=["numero_pedido", "data", "id_cliente", "sku", "quantidade", "preco_unitario"],
    ).assign(desconto_pct="0,00", forma_pagamento="PIX")

    ordens = []
    for cliente, inicio, vezes in [(1, date(2026, 1, 1), 7), (4, date(2025, 8, 3), 6)]:
        for k in range(vezes):
            d = inicio + timedelta(days=30 * k)
            ordens.append((cliente, d, "Concluída", "25,00", f"PLACA{cliente}"))
    ordens.append((2, date(2026, 6, 15), "Cancelada", "999,00", "PLACA2"))
    ordens = pd.DataFrame(
        ordens, columns=["id_cliente", "data", "status", "valor_mao_obra", "placa"]
    )
    ordens = ordens.assign(
        numero_os=range(1, len(ordens) + 1),
        data_abertura=ordens.data.map(data_br),
        data_conclusao=ordens.data.map(data_br),
        moto="Honda CG 160",
        servico="Troca de óleo",
        mecanico="Marcos",
        forma_pagamento="PIX",
    ).drop(columns="data")
    itens_os = pd.DataFrame(
        {"numero_os": [1], "sku": ["P-B"], "quantidade": [1], "preco_unitario": ["100,00"]}
    )

    for nome, df in [
        ("produtos", produtos),
        ("clientes", clientes),
        ("vendas", vendas),
        ("ordens_servico", ordens),
        ("itens_os", itens_os),
    ]:
        df.to_csv(pasta / f"{nome}.csv", sep=";", index=False)


@pytest.fixture(scope="module")
def cenario(tmp_path_factory):
    """Banco construído a partir do cenário montado à mão."""
    pasta = tmp_path_factory.mktemp("cenario")
    montar_csvs(pasta)
    conexao = duckdb.connect(construir_banco(pasta, pasta / "cenario.duckdb"), read_only=True)
    yield conexao
    conexao.close()


def linha(con, sql: str) -> dict:
    """Primeira linha de uma consulta como dicionário {coluna: valor}."""
    cursor = con.execute(sql)
    colunas = [c[0] for c in cursor.description]
    return dict(zip(colunas, cursor.fetchone(), strict=True))


# ---- Parte 1: cenário calculado à mão ------------------------------------------------


def test_data_de_referencia_e_a_ultima_movimentacao(cenario):
    ref = linha(cenario, "SELECT * FROM analise.referencia")
    assert ref["data_referencia"] == REFERENCIA
    assert ref["data_inicial"] == date(2025, 8, 3)  # 1ª OS do Pedro, que não tem peça


def test_curva_abc(cenario):
    # Receita 12m: P-B 800, P-A 200, P-E 60, P-C 40, P-D 0 -> total 1100.
    # Acumulado antes de cada item: P-B 0 (A), P-A 800 < 880 (A), P-E 1000 < 1045 (B),
    # P-C 1060 >= 1045 (C), P-D sem receita (C).
    classes = dict(cenario.execute("SELECT sku, classe_abc FROM analise.estoque").fetchall())
    assert classes == {"P-B": "A", "P-A": "A", "P-E": "B", "P-C": "C", "P-D": "C"}


def test_situacao_do_estoque(cenario):
    situacao = dict(cenario.execute("SELECT sku, situacao FROM analise.estoque").fetchall())
    assert situacao == {
        "P-B": "Ok",  # 20 em estoque, vendendo
        "P-A": "Repor",  # 2 < mínimo 5 e vendeu nos últimos 90 dias
        "P-E": "Em falta",  # zerado e vendeu nos últimos 90 dias
        "P-C": "Sem giro",  # 200 dias sem vender, 10 na prateleira
        "P-D": "Sem giro",  # nunca vendeu
    }


def test_dias_sem_venda_valor_parado_e_cobertura(cenario):
    p_c = linha(cenario, "SELECT * FROM analise.estoque WHERE sku = 'P-C'")
    p_d = linha(cenario, "SELECT * FROM analise.estoque WHERE sku = 'P-D'")
    p_b = linha(cenario, "SELECT * FROM analise.estoque WHERE sku = 'P-B'")
    assert p_c["dias_sem_venda"] == 200
    assert p_d["dias_sem_venda"] == 545  # desde o cadastro: 01/01/25 -> 30/06/26
    assert p_c["valor_estoque"] == 50  # 10 un. x R$ 5
    assert p_d["valor_estoque"] == 60  # 3 un. x R$ 20
    assert p_b["cobertura_dias"] == 257  # 20 un. / (7 un. em 90 dias) = 257,1 dias


def test_faturamento_de_junho(cenario):
    junho = linha(cenario, "SELECT * FROM analise.faturamento_mensal WHERE mes = '2026-06-01'")
    assert junho["pecas_balcao"] == 960  # 700 + 200 + 60
    assert junho["pecas_oficina"] == 0
    assert junho["mao_de_obra"] == 25  # só a OS de 30/06; a cancelada (R$ 999) fica fora
    assert junho["faturamento"] == 985
    assert junho["custo_pecas"] == 480  # 7x50 + 10x10 + 3x10
    assert junho["margem_pecas"] == 480
    assert junho["lucro_bruto"] == 505
    assert junho["qtd_pedidos"] == 3
    assert junho["qtd_os"] == 1
    assert junho["mes_completo"]


def test_mes_so_com_mao_de_obra_aparece_e_mes_parcial_e_sinalizado(cenario):
    agosto = linha(cenario, "SELECT * FROM analise.faturamento_mensal WHERE mes = '2025-08-01'")
    assert agosto["faturamento"] == 25
    assert not agosto["mes_completo"]  # dados começam em 03/08


def test_os_cancelada_nao_entra_em_nada(cenario):
    assert valor(cenario, "SELECT sum(mao_de_obra) FROM analise.faturamento_mensal") == 13 * 25


def test_perfil_e_status_dos_clientes(cenario):
    clientes = {
        r[0]: r[1:]
        for r in cenario.execute(
            "SELECT id_cliente, perfil, status, qtd_visitas, intervalo_medio_dias "
            "FROM analise.clientes_perfil"
        ).fetchall()
    }
    assert clientes[1] == ("Motoboy", "Ativo", 7, 30)
    assert clientes[2] == ("Uso pessoal", "Ativo", 3, 95)  # (20/06/26 - 12/12/25) / 2
    assert clientes[3][:2] == ("Frota", "Ativo")
    assert clientes[4] == ("Motoboy", "Inativo", 6, 30)  # 181 dias sem vir > 4 x 30


def test_gasto_do_cliente_inclui_pecas_e_mao_de_obra(cenario):
    gastos = dict(
        cenario.execute("SELECT id_cliente, gasto_total FROM analise.clientes_perfil").fetchall()
    )
    assert gastos[1] == 7 * 25 + 100
    assert gastos[2] == 200 + 60 + 40  # a OS cancelada não conta


# ---- Parte 2: dados completos x gabarito do gerador ----------------------------------


def test_perfil_descoberto_bate_com_o_real(con, verdade):
    real = verdade.clientes[["id_cliente", "perfil"]]
    inferido = con.execute("""
        SELECT id_cliente, perfil AS perfil_inferido, qtd_visitas
        FROM analise.clientes_perfil
        WHERE qtd_visitas >= 6  -- com poucas visitas não dá para saber a frequência
    """).df()
    juntos = inferido.merge(real, on="id_cliente")
    juntos["perfil"] = juntos.perfil.map(
        {"motoboy": "Motoboy", "pessoal": "Uso pessoal", "frota": "Frota"}
    )
    acerto = (juntos.perfil == juntos.perfil_inferido).mean()
    assert acerto >= 0.95


def test_encalhados_do_gerador_aparecem_sem_giro(con, verdade):
    encalhados = verdade.produtos.loc[
        verdade.produtos.sem_giro & (verdade.produtos.estoque_atual > 0), "sku"
    ]
    sem_giro = {
        r[0]
        for r in con.execute(
            "SELECT sku FROM analise.estoque WHERE situacao = 'Sem giro'"
        ).fetchall()
    }
    assert set(encalhados) <= sem_giro


def test_faturamento_mensal_soma_o_total(con):
    total_mensal = valor(con, "SELECT sum(faturamento) FROM analise.faturamento_mensal")
    pecas = valor(con, "SELECT sum(receita) FROM analise.itens_vendidos")
    mao = valor(con, "SELECT sum(valor_mao_obra) FROM analise.ordens_concluidas")
    assert total_mensal == pecas + mao


def test_classe_a_concentra_80_por_cento(con):
    participacao_a = valor(
        con,
        """
        SELECT sum(receita_12m) FILTER (WHERE classe_abc = 'A') / sum(receita_12m)
        FROM analise.estoque""",
    )
    assert 0.80 <= participacao_a <= 0.85
