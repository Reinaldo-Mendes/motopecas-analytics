"""Testes do gerador: garantem que os dados fictícios têm os achados que o diagnóstico precisa."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from faker import Faker

from gerar_dados import (
    aplicar_sujeira,
    gerar_clientes,
    gerar_produtos,
    remover_acentos,
    simular_dados,
    subtrair_meses,
)

DATA_FIM = date(2026, 11, 26)


@pytest.fixture(scope="module")
def dados():
    """Gera os dados uma vez só para todos os testes do arquivo (como um @BeforeAll)."""
    return simular_dados(seed=42, data_fim=DATA_FIM)


@pytest.fixture(scope="module")
def sujos(dados):
    """Versão 'exportada do ERP' dos mesmos dados."""
    return aplicar_sujeira(dados, seed=42)


def receita_por_sku(dados) -> pd.Series:
    """Receita de peças (balcão + OS não canceladas) por SKU, incluindo SKUs sem venda."""
    vendas = dados.vendas.assign(receita=lambda x: x.quantidade * x.preco_unitario)
    validas = dados.ordens_servico.loc[dados.ordens_servico.status != "Cancelada", "numero_os"]
    itens = dados.itens_os[dados.itens_os.numero_os.isin(validas)]
    itens = itens.assign(receita=lambda x: x.quantidade * x.preco_unitario)
    receita = pd.concat([vendas, itens]).groupby("sku")["receita"].sum()
    return receita.reindex(dados.produtos.sku, fill_value=0)


def test_subtrair_meses_ajusta_fim_de_mes():
    assert subtrair_meses(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert subtrair_meses(date(2026, 11, 26), 24) == date(2024, 11, 26)


def test_catalogo_e_clientes_sao_reproduziveis():
    inicio = subtrair_meses(DATA_FIM, 24)

    def gerar():
        rng = np.random.default_rng(1)
        fake = Faker("pt_BR")
        fake.seed_instance(1)
        return gerar_produtos(rng, inicio, DATA_FIM), gerar_clientes(fake, rng, inicio, DATA_FIM)

    (p1, c1), (p2, c2) = gerar(), gerar()
    pd.testing.assert_frame_equal(p1, p2)
    pd.testing.assert_frame_equal(
        c1.drop(columns=["motos", "placas"]), c2.drop(columns=["motos", "placas"])
    )


def test_catalogo_tem_cerca_de_400_skus_unicos(dados):
    assert 350 <= len(dados.produtos) <= 450
    assert dados.produtos.sku.is_unique
    assert dados.produtos.categoria.nunique() == 8


def test_periodo_de_24_meses_sem_domingos(dados):
    datas = pd.to_datetime(dados.vendas.data)
    assert datas.min().date() >= subtrair_meses(DATA_FIM, 24)
    assert datas.max().date() <= DATA_FIM
    assert (datas.dt.day_of_week != 6).all()


def test_curva_abc_aproximadamente_80_20(dados):
    receita = receita_por_sku(dados).sort_values(ascending=False)
    top_20 = receita.iloc[: int(len(receita) * 0.2)].sum() / receita.sum()
    assert 0.70 <= top_20 <= 0.90


def test_existe_estoque_parado_ha_6_meses(dados):
    corte = DATA_FIM - timedelta(days=180)
    itens_os = dados.itens_os.merge(dados.ordens_servico[["numero_os", "data_abertura"]])
    saidas = pd.concat(
        [
            dados.vendas[["sku", "data"]],
            itens_os.rename(columns={"data_abertura": "data"})[["sku", "data"]],
        ]
    )
    ultima = saidas.groupby("sku")["data"].max()
    produtos = dados.produtos.set_index("sku")
    sem_venda_recente = produtos.index.map(ultima).to_series(index=produtos.index)
    parado = produtos.estoque_atual.gt(0) & (sem_venda_recente.isna() | (sem_venda_recente < corte))
    assert parado.sum() >= 0.10 * len(produtos)


def test_pneus_vendem_mais_na_chuva(dados):
    vendas = dados.vendas.merge(dados.produtos[["sku", "categoria"]])
    vendas["receita"] = vendas.quantidade * vendas.preco_unitario
    vendas["chuva"] = pd.to_datetime(vendas.data).dt.month.isin([11, 12, 1, 2, 3])
    participacao = vendas.groupby("chuva").apply(
        lambda g: g.loc[g.categoria == "Pneus e câmaras", "receita"].sum() / g.receita.sum()
    )
    assert participacao[True] > participacao[False] * 1.15


def test_acessorios_tem_pico_em_dezembro(dados):
    vendas = dados.vendas.merge(dados.produtos[["sku", "categoria"]])
    acessorios = vendas[vendas.categoria == "Acessórios"]
    por_mes = acessorios.groupby(pd.to_datetime(acessorios.data).dt.month)["quantidade"].sum()
    assert por_mes.idxmax() == 12


def test_motoboy_troca_oleo_a_cada_30_dias(dados):
    motoboys = dados.clientes.loc[dados.clientes.perfil == "motoboy", "id_cliente"]
    os_oleo = dados.ordens_servico[
        dados.ordens_servico.id_cliente.isin(motoboys)
        & (dados.ordens_servico.servico == "Troca de óleo")
    ]
    intervalos = (
        pd.to_datetime(os_oleo.sort_values("data_abertura").data_abertura)
        .groupby(os_oleo.id_cliente)
        .diff()
        .dt.days.dropna()
    )
    assert 25 <= intervalos.median() <= 50  # parte das trocas vai pro balcão, alongando o intervalo


def test_oficina_tem_3_a_4_mecanicos(dados):
    assert 3 <= dados.ordens_servico.mecanico.nunique() <= 4


def test_sujeira_telefones_faltando(sujos):
    vazios = sujos["clientes"].telefone.eq("").mean()
    assert 0.05 <= vazios <= 0.30


def test_sujeira_nomes_duplicados_com_grafia_diferente(dados, sujos):
    clientes = sujos["clientes"]
    originais = dados.clientes.dropna(subset=["id_duplicado"])
    assert len(originais) > 20
    for _, original in originais.head(10).iterrows():
        copia = clientes.loc[clientes.id_cliente == original.id_duplicado, "nome"].iloc[0]
        assert copia != original.nome
        primeiro = remover_acentos(original.nome.split()[0]).lower()
        assert remover_acentos(copia).lower().startswith(primeiro)


def test_sujeira_datas_em_formatos_mistos(sujos):
    datas = sujos["vendas"].data
    assert datas.str.match(r"^\d{2}/\d{2}/\d{4}$").any()
    assert datas.str.match(r"^\d{4}-\d{2}-\d{2}$").any()
    assert datas.str.match(r"^\d{2}/\d{2}/\d{2}$").any()


def test_sujeira_precos_zerados(sujos):
    assert sujos["vendas"].preco_unitario.eq("0,00").any()
    assert sujos["produtos"].preco_venda.isin(["0,00", "R$ 0,00"]).any()
