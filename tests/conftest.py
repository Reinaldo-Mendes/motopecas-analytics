"""Fixtures compartilhadas por todos os testes (o pytest carrega este arquivo sozinho)."""

import duckdb
import pytest

from gerar_dados import aplicar_sujeira, salvar_csvs, simular_dados
from pipeline import construir_banco


@pytest.fixture(scope="session")
def verdade():
    """Dados limpos do gerador: o gabarito que a limpeza deve reconstruir."""
    return simular_dados(seed=42)


@pytest.fixture(scope="session")
def con(verdade, tmp_path_factory):
    """Gera CSVs sujos numa pasta temporária, roda o pipeline e abre o banco resultante."""
    pasta = tmp_path_factory.mktemp("dados")
    salvar_csvs(aplicar_sujeira(verdade, seed=42), pasta)
    banco = construir_banco(pasta_brutos=pasta, caminho_banco=pasta / "teste.duckdb")
    conexao = duckdb.connect(banco, read_only=True)
    yield conexao  # o código depois do yield roda no fim, como um @AfterAll
    conexao.close()


def valor(con, sql: str):
    """Executa uma consulta que devolve um único valor."""
    return con.execute(sql).fetchone()[0]
