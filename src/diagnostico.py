"""Resumos e "achados" do diagnóstico, em texto pronto para o dashboard e o bot.

Cada função recebe uma conexão DuckDB aberta e lê as views do schema `analise`.
"""

from __future__ import annotations

import duckdb

from formatacao import formatar_mes, formatar_moeda_curta, formatar_numero, formatar_pct


def consultar_linha(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    """Primeira linha de uma consulta como dicionário {coluna: valor}."""
    cursor = con.execute(sql)
    colunas = [c[0] for c in cursor.description]
    linha = cursor.fetchone()
    return dict(zip(colunas, linha, strict=True)) if linha else {}


def consultar_linhas(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    """Todas as linhas de uma consulta como lista de dicionários."""
    cursor = con.execute(sql)
    colunas = [c[0] for c in cursor.description]
    return [dict(zip(colunas, linha, strict=True)) for linha in cursor.fetchall()]


def resumo_semana(con: duckdb.DuckDBPyConnection) -> dict:
    """Últimos 7 dias com dados x 7 dias anteriores: faturamento e OS concluídas."""
    return consultar_linha(
        con,
        """
        WITH movimento AS (
            SELECT data, receita AS valor, 0 AS os FROM analise.itens_vendidos
            UNION ALL
            SELECT data_abertura, valor_mao_obra, 1 FROM analise.ordens_concluidas
        )
        SELECT
            r.data_referencia - 6 AS inicio,
            r.data_referencia AS fim,
            sum(m.valor) FILTER (WHERE m.data > r.data_referencia - 7) AS faturamento,
            sum(m.valor) FILTER (WHERE m.data > r.data_referencia - 14
                                   AND m.data <= r.data_referencia - 7) AS faturamento_anterior,
            sum(m.os) FILTER (WHERE m.data > r.data_referencia - 7) AS qtd_os,
            sum(m.os) FILTER (WHERE m.data > r.data_referencia - 14
                                AND m.data <= r.data_referencia - 7) AS qtd_os_anterior
        FROM movimento AS m
        CROSS JOIN analise.referencia AS r
        GROUP BY r.data_referencia
    """,
    )


def itens_em_falta(con: duckdb.DuckDBPyConnection, limite: int = 5) -> list[dict]:
    """Itens zerados com saída recente, os que mais faturam primeiro (curva A no topo)."""
    return consultar_linhas(
        con,
        f"""
        SELECT descricao, classe_abc, qtd_vendida_90d
        FROM analise.estoque
        WHERE situacao = 'Em falta'
        ORDER BY classe_abc, receita_12m DESC
        LIMIT {int(limite)}
    """,
    )


def clientes_para_ligar(con: duckdb.DuckDBPyConnection, limite: int = 5) -> list[dict]:
    """Clientes 'em risco' (começaram a sumir), dos que mais gastam para os que menos.

    'Em risco' e não 'inativo': quem parou há pouco tempo ainda tem boa chance de voltar.
    """
    return consultar_linhas(
        con,
        f"""
        SELECT nome, telefone, perfil, dias_desde_ultima_visita, gasto_12m
        FROM analise.clientes_perfil
        WHERE status = 'Em risco'
        ORDER BY gasto_12m DESC
        LIMIT {int(limite)}
    """,
    )


def resumo_meses(con: duckdb.DuckDBPyConnection) -> dict:
    """Último mês completo e o anterior, para comparar (ex.: out/2026 x set/2026)."""
    meses = con.execute("""
        SELECT mes, faturamento, margem_pecas_pct, lucro_bruto, qtd_os, qtd_pedidos
        FROM analise.faturamento_mensal
        WHERE mes_completo
        ORDER BY mes DESC
        LIMIT 2
    """).fetchall()
    colunas = ["mes", "faturamento", "margem_pecas_pct", "lucro_bruto", "qtd_os", "qtd_pedidos"]
    atual, anterior = (dict(zip(colunas, m, strict=True)) for m in meses)
    return {"atual": atual, "anterior": anterior}


def resumo_estoque(con: duckdb.DuckDBPyConnection) -> dict:
    """Totais do estoque por situação."""
    return consultar_linha(
        con,
        """
        SELECT
            sum(valor_estoque) AS valor_total,
            sum(valor_estoque) FILTER (WHERE situacao = 'Sem giro') AS valor_parado,
            count(*) FILTER (WHERE situacao = 'Sem giro') AS qtd_sem_giro,
            count(*) FILTER (WHERE situacao = 'Em falta') AS qtd_em_falta,
            count(*) FILTER (WHERE situacao = 'Em falta' AND classe_abc = 'A') AS qtd_em_falta_a,
            count(*) FILTER (WHERE situacao = 'Repor') AS qtd_repor,
            count(*) AS qtd_skus
        FROM analise.estoque
    """,
    )


def resumo_clientes(con: duckdb.DuckDBPyConnection) -> dict:
    """Clientes por perfil e quantos motoboys deixaram de vir no último ano."""
    return consultar_linha(
        con,
        """
        SELECT
            count(*) FILTER (WHERE status = 'Ativo') AS ativos,
            count(*) FILTER (WHERE perfil = 'Motoboy' AND status = 'Ativo') AS motoboys_ativos,
            count(*) FILTER (WHERE perfil = 'Motoboy' AND status IN ('Em risco', 'Inativo')
                             AND dias_desde_ultima_visita <= 365) AS motoboys_sumidos,
            sum(gasto_12m) FILTER (WHERE perfil = 'Motoboy' AND status IN ('Em risco', 'Inativo')
                                   AND dias_desde_ultima_visita <= 365) AS gasto_motoboys_sumidos,
            count(*) FILTER (WHERE status = 'Em risco') AS em_risco
        FROM analise.clientes_perfil
    """,
    )


def concentracao_abc(con: duckdb.DuckDBPyConnection) -> dict:
    """Quantos SKUs da classe A existem e quanto da receita eles fazem."""
    return consultar_linha(
        con,
        """
        SELECT
            count(*) FILTER (WHERE classe_abc = 'A') AS qtd_a,
            count(*) AS qtd_total,
            sum(receita_12m) FILTER (WHERE classe_abc = 'A') / sum(receita_12m) AS receita_a_pct
        FROM analise.estoque
    """,
    )


def categoria_destaque(con: duckdb.DuckDBPyConnection) -> dict:
    """Categoria que mais fatura e a margem dela, comparada à margem média."""
    return consultar_linha(
        con,
        """
        SELECT
            categoria, participacao_receita, margem_pct,
            (SELECT sum(margem) / sum(receita) FROM analise.margem_categoria) AS margem_media
        FROM analise.margem_categoria
        ORDER BY receita DESC
        LIMIT 1
    """,
    )


def principais_achados(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Frases curtas com o que o dono da loja precisa saber, da mais urgente para a menos."""
    estoque = resumo_estoque(con)
    clientes = resumo_clientes(con)
    abc = concentracao_abc(con)
    destaque = categoria_destaque(con)
    meses = resumo_meses(con)

    achados = [
        f"{formatar_moeda_curta(estoque['valor_parado'])} parados em "
        f"{estoque['qtd_sem_giro']} itens que não vendem há 6 meses ou mais.",
    ]
    if estoque["qtd_em_falta"]:
        achados.append(
            f"{estoque['qtd_em_falta']} itens com saída recente estão zerados no estoque"
            f" ({estoque['qtd_em_falta_a']} deles da curva A): é venda perdida."
        )
    if clientes["motoboys_sumidos"]:
        achados.append(
            f"{clientes['motoboys_sumidos']} motoboys que vinham todo mês pararam de aparecer"
            f" (gastaram {formatar_moeda_curta(clientes['gasto_motoboys_sumidos'])}"
            " nos últimos 12 meses)."
        )
    achados.append(
        f"Só {abc['qtd_a']} dos {abc['qtd_total']} itens ({
            formatar_pct(abc['qtd_a'] / abc['qtd_total'], 0)
        }) fazem {formatar_pct(abc['receita_a_pct'], 0)} da receita:"
        " são esses que nunca podem faltar."
    )
    achados.append(
        f"{destaque['categoria']} é a categoria que mais fatura"
        f" ({formatar_pct(destaque['participacao_receita'], 0)} da receita), mas tem margem de"
        f" {formatar_pct(destaque['margem_pct'], 0)}, contra"
        f" {formatar_pct(destaque['margem_media'], 0)} na média da loja."
    )
    atual, anterior = meses["atual"], meses["anterior"]
    variacao = atual["faturamento"] / anterior["faturamento"] - 1
    direcao = "acima" if variacao >= 0 else "abaixo"
    achados.append(
        f"Faturamento de {formatar_mes(atual['mes'])}: "
        f"{formatar_moeda_curta(atual['faturamento'])}, {formatar_pct(abs(variacao), 0)}"
        f" {direcao} de {formatar_mes(anterior['mes'])}"
        f" ({formatar_numero(atual['qtd_os'])} OS na oficina)."
    )
    return achados
