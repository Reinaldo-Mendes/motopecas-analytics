"""Resumos e "achados" do diagnóstico, em texto pronto para o dashboard e o bot.

Cada função recebe uma conexão DuckDB aberta e lê as views do schema `analise`.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from formatacao import formatar_moeda, formatar_moeda_curta, formatar_numero, formatar_pct


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


def troca_oleo_semana(con: duckdb.DuckDBPyConnection, limite: int | None = 5) -> list[dict]:
    """Clientes com troca de óleo prevista para esta semana ou atrasada há até 15 dias.

    Ordem: quem mais gasta primeiro (é para quem vale mais a pena mandar mensagem).
    """
    limite_sql = f"LIMIT {int(limite)}" if limite else ""
    return consultar_linhas(
        con,
        f"""
        SELECT nome, telefone, perfil, moto_principal, ultima_troca, proxima_troca,
               dias_para_troca, intervalo_dias, situacao, gasto_12m
        FROM analise.clientes_troca_oleo
        WHERE situacao IN ('Esta semana', 'Atrasada')
        ORDER BY gasto_12m DESC
        {limite_sql}
    """,
    )


def resumo_troca_oleo(con: duckdb.DuckDBPyConnection) -> dict:
    """Quantos clientes trocam óleo esta semana, quantos atrasaram e o ticket médio da troca."""
    return consultar_linha(
        con,
        """
        SELECT
            count(*) FILTER (WHERE situacao = 'Esta semana') AS qtd_esta_semana,
            count(*) FILTER (WHERE situacao = 'Atrasada') AS qtd_atrasada,
            (SELECT avg(valor_total) FROM analise.ordens_concluidas
             WHERE servico = 'Troca de óleo') AS ticket_troca
        FROM analise.clientes_troca_oleo
    """,
    )


def resumo_cancelamentos(con: duckdb.DuckDBPyConnection) -> dict:
    """Valor perdido em OS canceladas (12 meses) e a taxa nos orçamentos baratos x caros."""
    return consultar_linha(
        con,
        """
        SELECT
            sum(valor_perdido) AS valor_perdido,
            sum(qtd_canceladas) AS qtd_canceladas,
            min(taxa_cancelamento) FILTER (WHERE faixa_orcamento LIKE '1.%') AS taxa_barato,
            min(taxa_cancelamento) FILTER (WHERE faixa_orcamento LIKE '4.%') AS taxa_caro
        FROM analise.cancelamento_por_faixa
    """,
    )


def resumo_prazo(con: duckdb.DuckDBPyConnection) -> dict:
    """Mecânico mais lento (fora a troca de óleo) e a média dos demais."""
    return consultar_linha(
        con,
        """
        SELECT
            arg_max(mecanico, dias_medios) AS mecanico,
            max(dias_medios) AS dias_medios,
            (sum(dias_medios * qtd_os) - arg_max(dias_medios * qtd_os, dias_medios))
                / (sum(qtd_os) - arg_max(qtd_os, dias_medios)) AS dias_demais
        FROM analise.oficina_prazo
    """,
    )


def resumo_venda_casada(con: duckdb.DuckDBPyConnection) -> dict:
    """Receita potencial somada e os pares serviço + item, do maior potencial ao menor."""
    pares = consultar_linhas(con, "SELECT * FROM analise.oficina_venda_casada")
    return {
        "receita_potencial": sum(p["receita_potencial_12m"] for p in pares),
        "pares": pares,
    }


def resumo_descontos(con: duckdb.DuckDBPyConnection) -> dict:
    """Descontos do balcão nos últimos 12 meses: total, quem recebe e efeito no ticket."""
    return consultar_linha(
        con,
        """
        SELECT
            sum(d.valor_desconto) AS valor_desconto,
            avg((d.desconto_pct > 0)::INTEGER) AS pedidos_com_desconto_pct,
            avg(d.receita) FILTER (WHERE d.desconto_pct > 0) AS ticket_com_desconto,
            avg(d.receita) FILTER (WHERE d.desconto_pct = 0) AS ticket_sem_desconto,
            (SELECT min(pedidos_com_desconto_pct) FROM analise.descontos_por_perfil) AS pct_min,
            (SELECT max(pedidos_com_desconto_pct) FROM analise.descontos_por_perfil) AS pct_max
        FROM analise.pedidos_desconto AS d
        CROSS JOIN analise.referencia AS r
        WHERE d.data > r.data_referencia - 365
    """,
    )


def resumo_recebimentos(con: duckdb.DuckDBPyConnection) -> dict:
    """Custo estimado das formas de pagamento (12 meses), com destaque para o crédito."""
    return consultar_linha(
        con,
        """
        SELECT
            sum(custo_estimado) AS custo_total,
            sum(custo_estimado) FILTER (WHERE forma_pagamento = 'Cartão de crédito')
                AS custo_credito,
            sum(participacao) FILTER (WHERE forma_pagamento = 'Cartão de crédito')
                AS participacao_credito,
            max(taxa_pct) AS taxa_credito
        FROM analise.recebimentos
    """,
    )


def resumo_estoque_moto(con: duckdb.DuckDBPyConnection, qtd_motos: int = 2) -> dict:
    """As motos que menos passam pela oficina: quanto do estoque parado é delas."""
    motos = consultar_linhas(
        con,
        f"""
        SELECT moto, valor_parado, participacao_parado, participacao_os
        FROM analise.estoque_por_moto
        ORDER BY participacao_os
        LIMIT {int(qtd_motos)}
    """,
    )
    return {
        "motos": [m["moto"] for m in motos],
        "valor_parado": sum(m["valor_parado"] for m in motos),
        "participacao_parado": sum(m["participacao_parado"] for m in motos),
        "participacao_os": sum(m["participacao_os"] for m in motos),
    }


@dataclass(frozen=True)
class Achado:
    """Um achado do diagnóstico, pronto para virar cartão (parecido com um `record` do Java).

    tipo: 'alerta' (dinheiro perdido ou parado), 'oportunidade' (dinheiro a ganhar) ou
    'info' (contexto). impacto: valor em R$ por ano, usado só para ordenar.
    """

    tema: str
    valor: str
    texto: str
    tipo: str
    pagina: str
    impacto: float = 0.0


def juntar(itens: list[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b e c'."""
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def modelo(moto: str) -> str:
    """'Yamaha Fazer 250' -> 'Fazer 250' (marca sobra no texto curto)."""
    return moto.split(" ", 1)[1]


def principais_achados(con: duckdb.DuckDBPyConnection) -> list[Achado]:
    """Achados do diagnóstico: primeiro os de maior impacto em R$, depois os de contexto."""
    estoque = resumo_estoque(con)
    clientes = resumo_clientes(con)
    abc = concentracao_abc(con)
    destaque = categoria_destaque(con)
    cancel = resumo_cancelamentos(con)
    prazo = resumo_prazo(con)
    casada = resumo_venda_casada(con)
    desconto = resumo_descontos(con)
    pagamento = resumo_recebimentos(con)
    por_moto = resumo_estoque_moto(con)
    falta = consultar_linha(
        con, "SELECT sum(receita_12m) AS receita FROM analise.estoque WHERE situacao = 'Em falta'"
    )

    achados = [
        Achado(
            "Estoque parado",
            formatar_moeda_curta(estoque["valor_parado"]),
            f"em {estoque['qtd_sem_giro']} itens que não vendem há 6 meses ou mais. Promoção, "
            "kit ou devolução ao fornecedor liberam esse dinheiro.",
            "alerta",
            "estoque",
            float(estoque["valor_parado"]),
        ),
        Achado(
            "Estoque fora da frota",
            formatar_pct(por_moto["participacao_parado"], 0),
            "do estoque parado é de peças para "
            f"{juntar([modelo(m) for m in por_moto['motos']])}, que são só "
            f"{formatar_pct(por_moto['participacao_os'], 0)} das motos atendidas na oficina. "
            "Para essas motos, vale comprar sob encomenda.",
            "alerta",
            "estoque",
            float(por_moto["valor_parado"]),
        ),
        Achado(
            "Orçamentos recusados",
            formatar_moeda_curta(cancel["valor_perdido"]),
            f"em OS canceladas nos últimos 12 meses. Acima de R$ 500 o cliente desiste "
            f"{formatar_pct(cancel['taxa_caro'], 0)} das vezes, contra "
            f"{formatar_pct(cancel['taxa_barato'], 0)} até R$ 150: parcelar ou dividir o "
            "serviço em etapas segura a venda.",
            "alerta",
            "oficina",
            float(cancel["valor_perdido"]),
        ),
        Achado(
            "Venda casada",
            f"+{formatar_moeda_curta(casada['receita_potencial'])}/ano",
            "se a oficina oferecesse a peça que combina com cada serviço. Hoje só "
            f"{formatar_pct(casada['pares'][0]['taxa_atual'], 0)} das trocas de óleo levam "
            "filtro"
            + (
                ", e "
                + juntar([p["item"].lower() for p in casada["pares"] if p["qtd_com_item"] == 0])
                + " nunca saem junto com o serviço"
                if any(p["qtd_com_item"] == 0 for p in casada["pares"])
                else ""
            )
            + ".",
            "oportunidade",
            "oficina",
            float(casada["receita_potencial"]),
        ),
    ]
    if estoque["qtd_em_falta"]:
        achados.append(
            Achado(
                "Venda perdida",
                f"{estoque['qtd_em_falta']} itens",
                f"com saída recente estão zerados ({estoque['qtd_em_falta_a']} da curva A). "
                f"Juntos, vendem {formatar_moeda_curta(falta['receita'] / 12)} por mês: cada "
                "semana zerado é venda que vai para o concorrente.",
                "alerta",
                "estoque",
                float(falta["receita"]) / 12,  # o que se perde por mês enquanto falta
            )
        )
    if clientes["motoboys_sumidos"]:
        achados.append(
            Achado(
                "Clientes sumindo",
                f"{clientes['motoboys_sumidos']} motoboys",
                "que vinham todo mês pararam de aparecer. Gastaram "
                f"{formatar_moeda_curta(clientes['gasto_motoboys_sumidos'])} nos últimos "
                "12 meses.",
                "alerta",
                "clientes",
                float(clientes["gasto_motoboys_sumidos"]),
            )
        )
    achados += [
        Achado(
            "Desconto sem critério",
            formatar_moeda_curta(desconto["valor_desconto"]),
            "em descontos no balcão em 12 meses, dados em "
            f"{formatar_pct(desconto['pct_min'], 0)} a {formatar_pct(desconto['pct_max'], 0)} "
            "dos pedidos de todo tipo de cliente. E o pedido com desconto não é maior: ticket de "
            f"{formatar_moeda(desconto['ticket_com_desconto'])}, contra "
            f"{formatar_moeda(desconto['ticket_sem_desconto'])} sem desconto.",
            "oportunidade",
            "vendas",
            float(desconto["valor_desconto"]),
        ),
        Achado(
            "Taxa do cartão",
            formatar_moeda_curta(pagamento["custo_credito"]),
            "por ano em taxa do cartão de crédito (estimativa de "
            f"{formatar_pct(pagamento['taxa_credito'])} sobre "
            f"{formatar_pct(pagamento['participacao_credito'], 0)} do faturamento). Dar o "
            "desconto só no PIX troca um custo pelo outro.",
            "oportunidade",
            "vendas",
            float(pagamento["custo_credito"]),
        ),
    ]
    achados.sort(key=lambda a: a.impacto, reverse=True)

    achados += [
        Achado(
            "Prazo da oficina",
            f"{formatar_numero(prazo['dias_medios'], 1)} dias",
            f"é o prazo médio de {prazo['mecanico']} nos serviços além da troca de óleo, contra "
            f"{formatar_numero(prazo['dias_demais'], 1)} dos outros mecânicos.",
            "info",
            "oficina",
        ),
        Achado(
            "Itens que não podem faltar",
            f"{abc['qtd_a']} itens",
            f"({formatar_pct(abc['qtd_a'] / abc['qtd_total'], 0)} do catálogo) fazem "
            f"{formatar_pct(abc['receita_a_pct'], 0)} da receita: é a curva A.",
            "info",
            "estoque",
        ),
    ]
    # Só vira achado se a margem da categoria campeã destoa da média (5+ p.p.)
    if abs(destaque["margem_pct"] - destaque["margem_media"]) >= 0.05:
        achados.append(
            Achado(
                "Margem da maior categoria",
                formatar_pct(destaque["margem_pct"], 0),
                f"é a margem de {destaque['categoria']}, a categoria que mais fatura "
                f"({formatar_pct(destaque['participacao_receita'], 0)} da receita), contra "
                f"{formatar_pct(destaque['margem_media'], 0)} na média da loja.",
                "info",
                "vendas",
            )
        )
    return achados
