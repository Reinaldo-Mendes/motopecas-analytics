"""Carrega os CSVs brutos no DuckDB e executa as transformações de `src/sql/` em ordem.

O banco é sempre reconstruído do zero (o pipeline é idempotente: rodar duas vezes dá o mesmo
resultado). A construção acontece num arquivo temporário que só substitui o banco final no
fim, para nunca deixar um banco pela metade.

Uso:
    uv run python src/pipeline.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
PASTA_BRUTOS = RAIZ / "data" / "raw"
PASTA_SQL = Path(__file__).resolve().parent / "sql"
CAMINHO_BANCO = RAIZ / "data" / "motopecas.duckdb"
TABELAS_BRUTAS = ("produtos", "clientes", "vendas", "ordens_servico", "itens_os")


def carregar_brutos(con: duckdb.DuckDBPyConnection, pasta: Path) -> None:
    """Copia cada CSV para o schema `bruto`, tudo como texto (a tipagem é feita no SQL)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS bruto")
    for nome in TABELAS_BRUTAS:
        caminho = (pasta / f"{nome}.csv").as_posix()
        con.execute(
            f"CREATE OR REPLACE TABLE bruto.{nome} AS "
            "SELECT * FROM read_csv(?, delim = ';', header = true, all_varchar = true)",
            [caminho],
        )


def executar_sql(con: duckdb.DuckDBPyConnection, pasta: Path) -> list[str]:
    """Executa os arquivos .sql em ordem alfabética (por isso o prefixo 01_, 02_...)."""
    arquivos = sorted(pasta.glob("*.sql"))
    for arquivo in arquivos:
        con.execute(arquivo.read_text(encoding="utf-8"))
    return [a.name for a in arquivos]


def impressao_digital(pasta_brutos: Path = PASTA_BRUTOS, pasta_sql: Path = PASTA_SQL) -> str:
    """Hash (resumo SHA-256) do conteúdo dos CSVs e dos SQL que geram o banco.

    Se qualquer um desses arquivos mudar, o hash muda: é assim que o dashboard percebe que o
    banco salvo foi feito com dados ou SQL antigos e precisa ser reconstruído.
    """
    resumo = hashlib.sha256()
    arquivos = [pasta_brutos / f"{nome}.csv" for nome in TABELAS_BRUTAS]
    arquivos += sorted(pasta_sql.glob("*.sql"))
    for arquivo in arquivos:
        resumo.update(arquivo.name.encode())
        resumo.update(arquivo.read_bytes())
    return resumo.hexdigest()


def banco_atualizado(
    caminho_banco: Path = CAMINHO_BANCO,
    pasta_brutos: Path = PASTA_BRUTOS,
    pasta_sql: Path = PASTA_SQL,
) -> bool:
    """True se o banco existe e foi construído com os CSVs e SQL atuais."""
    if not caminho_banco.exists():
        return False
    try:
        with duckdb.connect(caminho_banco, read_only=True) as con:
            salvo = con.execute("SELECT impressao_digital FROM meta.versao").fetchone()[0]
    except duckdb.Error:  # banco antigo, sem a tabela meta.versao
        return False
    return salvo == impressao_digital(pasta_brutos, pasta_sql)


def construir_banco(
    pasta_brutos: Path = PASTA_BRUTOS,
    caminho_banco: Path = CAMINHO_BANCO,
    pasta_sql: Path = PASTA_SQL,
) -> Path:
    """Reconstrói o banco analítico completo e devolve o caminho dele."""
    temporario = caminho_banco.with_suffix(".tmp.duckdb")
    temporario.unlink(missing_ok=True)
    with duckdb.connect(temporario) as con:
        carregar_brutos(con, pasta_brutos)
        for nome in executar_sql(con, pasta_sql):
            print(f"  ok  {nome}")
        con.execute("CREATE SCHEMA IF NOT EXISTS meta")
        con.execute(
            "CREATE OR REPLACE TABLE meta.versao AS SELECT ? AS impressao_digital",
            [impressao_digital(pasta_brutos, pasta_sql)],
        )
    temporario.replace(caminho_banco)
    return caminho_banco


def imprimir_resumo(caminho_banco: Path) -> None:
    """Mostra o relatório de qualidade dos dados no terminal."""
    with duckdb.connect(caminho_banco, read_only=True) as con:
        print("\nQualidade dos dados brutos:")
        for problema, quantidade in con.execute("SELECT * FROM analise.qualidade_dados").fetchall():
            print(f"  {quantidade:>6}  {problema}")


def main() -> None:
    """Ponto de entrada da linha de comando."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # acentos corretos no terminal do Windows
    print("Construindo o banco analítico...")
    caminho = construir_banco()
    print(f"Banco gerado em {caminho.relative_to(RAIZ)}")
    imprimir_resumo(caminho)


if __name__ == "__main__":
    main()
