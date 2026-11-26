"""Testes do pipeline: a limpeza precisa recuperar os números dos dados limpos originais."""

import pandas as pd
import pytest

from conftest import valor


def test_todas_as_datas_foram_interpretadas(con):
    assert valor(con, "SELECT count(*) FROM limpo.vendas WHERE data IS NULL") == 0
    assert valor(con, "SELECT count(*) FROM limpo.ordens_servico WHERE data_abertura IS NULL") == 0
    assert valor(con, "SELECT count(*) FROM limpo.clientes WHERE data_cadastro IS NULL") == 0


def test_datas_batem_com_o_gabarito(con, verdade):
    limpas = con.execute("SELECT numero_pedido, data FROM limpo.vendas").df().drop_duplicates()
    esperadas = verdade.vendas[["numero_pedido", "data"]].drop_duplicates()
    juntas = limpas.merge(esperadas, on="numero_pedido", suffixes=("", "_esperada"))
    assert len(juntas) == len(esperadas)
    assert (pd.to_datetime(juntas.data) == pd.to_datetime(juntas.data_esperada)).all()


def test_nenhum_preco_zerado_apos_limpeza(con):
    assert valor(con, "SELECT min(preco_unitario) FROM limpo.vendas") > 0
    assert valor(con, "SELECT min(preco_unitario) FROM limpo.itens_os") > 0


def test_receita_do_balcao_bate_com_o_gabarito(con, verdade):
    esperada = (verdade.vendas.quantidade * verdade.vendas.preco_unitario).sum()
    obtida = float(
        valor(con, "SELECT sum(receita) FROM analise.itens_vendidos WHERE origem = 'Balcão'")
    )
    assert obtida == pytest.approx(esperada, rel=1e-4)


def test_receita_de_pecas_da_oficina_bate_com_o_gabarito(con, verdade):
    concluidas = verdade.ordens_servico.loc[
        verdade.ordens_servico.status == "Concluída", "numero_os"
    ]
    itens = verdade.itens_os[verdade.itens_os.numero_os.isin(concluidas)]
    esperada = (itens.quantidade * itens.preco_unitario).sum()
    obtida = float(
        valor(con, "SELECT sum(receita) FROM analise.itens_vendidos WHERE origem = 'Oficina'")
    )
    assert obtida == pytest.approx(esperada, rel=1e-3)


def test_os_canceladas_ficam_fora(con):
    sql = """SELECT count(*) FROM analise.ordens_concluidas o
             JOIN limpo.ordens_servico s USING (numero_os) WHERE s.status <> 'Concluída'"""
    assert valor(con, sql) == 0


def test_valor_total_da_os_e_mao_de_obra_mais_pecas(con):
    sql = """SELECT count(*) FROM analise.ordens_concluidas
             WHERE valor_total <> valor_mao_obra + valor_pecas"""
    assert valor(con, sql) == 0


def test_telefones_padronizados_com_ddd(con):
    sql = """SELECT count(*) FROM limpo.clientes
             WHERE telefone IS NOT NULL AND NOT regexp_full_match(telefone, '35\\d{9}')"""
    assert valor(con, sql) == 0


def test_unificacao_nao_junta_pessoas_diferentes(con, verdade):
    gabarito = verdade.clientes.dropna(subset=["id_duplicado"])
    pares_reais = {
        (int(d), int(o)) for o, d in zip(gabarito.id_cliente, gabarito.id_duplicado, strict=True)
    }
    unificados = con.execute("""
        SELECT id_cliente, id_cliente_unificado
        FROM limpo.clientes_unificados
        WHERE id_cliente <> id_cliente_unificado
    """).fetchall()
    assert set(unificados) <= pares_reais  # precisão de 100%: nenhum falso positivo
    assert len(unificados) >= 0.8 * len(pares_reais)  # e acha a grande maioria


def test_cadastro_consolidado_tem_uma_linha_por_pessoa(con):
    total = valor(con, "SELECT count(*) FROM limpo.clientes")
    unificados = valor(
        con,
        """SELECT count(*) FROM limpo.clientes_unificados
                               WHERE id_cliente <> id_cliente_unificado""",
    )
    assert valor(con, "SELECT count(*) FROM limpo.clientes_consolidados") == total - unificados


def test_produtos_sem_preco_sao_sinalizados(con):
    zerados = valor(
        con,
        """SELECT count(*) FROM bruto.produtos
                            WHERE preco_venda IN ('0,00', 'R$ 0,00')""",
    )
    assert zerados > 0
    assert valor(con, "SELECT count(*) FROM limpo.produtos WHERE preco_pendente") == zerados
