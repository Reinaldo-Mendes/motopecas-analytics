"""Vendas e margem: evolução mensal, margem, descontos, formas de pagamento e sazonalidade."""

import streamlit as st

from componentes import cabecalho, secao
from dados import calcular, consultar
from diagnostico import resumo_descontos, resumo_recebimentos
from formatacao import (
    MESES_ABREV,
    formatar_mes,
    formatar_moeda,
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
)
from graficos import NEUTRO, SERIES, barras_empilhadas, barras_horizontais, linha, mostrar

cabecalho("Vendas e margem", "Quanto entra, quanto sobra e o que come a margem no caminho.")

periodo = (
    st.segmented_control(
        "Período", ["Últimos 12 meses", "Últimos 24 meses"], default="Últimos 12 meses"
    )
    or "Últimos 12 meses"
)
dias = 365 if periodo == "Últimos 12 meses" else 730
filtro_data = f"data > (SELECT data_referencia FROM analise.referencia) - {dias}"

fat = consultar(f"""
    SELECT * FROM analise.faturamento_mensal
    WHERE mes > (SELECT date_trunc('month', data_referencia) FROM analise.referencia)
                - INTERVAL {dias // 30} MONTH
    ORDER BY mes
""")
itens = consultar(f"SELECT * FROM analise.itens_vendidos WHERE {filtro_data}")
pedidos = consultar(f"""
    SELECT count(DISTINCT numero_pedido) AS qtd, sum(quantidade * preco_unitario) AS receita
    FROM limpo.vendas WHERE {filtro_data}
""").iloc[0]
mao = (
    consultar(f"""SELECT sum(valor_mao_obra) AS v FROM analise.ordens_concluidas
                    WHERE data_abertura > (SELECT data_referencia FROM analise.referencia) - {dias}
                 """)
    .iloc[0]
    .v
)

receita_pecas = itens.receita.sum()
custo = itens.custo_total.sum()
col1, col2 = st.columns(2)
col1.metric(
    "Faturamento",
    formatar_moeda_curta(receita_pecas + mao),
    border=True,
    help="Peças (balcão + oficina) + mão de obra.",
)
col2.metric(
    "Lucro bruto",
    formatar_moeda_curta(receita_pecas + mao - custo),
    border=True,
    help="Faturamento menos o custo das peças.",
)
col1, col2 = st.columns(2)
col1.metric(
    "Margem das peças",
    formatar_pct((receita_pecas - custo) / receita_pecas),
    border=True,
    help="(Preço de venda - custo) / preço de venda.",
)
col2.metric(
    "Ticket médio no balcão",
    formatar_moeda(pedidos.receita / pedidos.qtd),
    border=True,
    help="Valor médio de cada pedido de balcão.",
)

# ---- Evolução ----
secao("Faturamento por mês", "Barras claras = mês incompleto.")
rotulos = [formatar_mes(m) for m in fat.mes]
mostrar(
    barras_empilhadas(
        rotulos,
        {
            "Peças no balcão": fat.pecas_balcao.tolist(),
            "Peças na oficina": fat.pecas_oficina.tolist(),
            "Mão de obra": fat.mao_de_obra.tolist(),
        },
        completos=fat.mes_completo.tolist(),
    ),
    fat.assign(
        Mês=rotulos,
        Faturamento=fat.faturamento.map(formatar_moeda),
        **{"Lucro bruto": fat.lucro_bruto.map(formatar_moeda)},
    )[["Mês", "Faturamento", "Lucro bruto"]],
)

secao("Margem das peças por mês")
completos = fat[fat.mes_completo]
margens = completos.margem_pecas_pct * 100
fig = linha(
    [formatar_mes(m) for m in completos.mes],
    margens.tolist(),
    "Margem",
    formato_y=",.0f",
    sufixo="%",
    rotulo_final=formatar_pct(completos.margem_pecas_pct.iloc[-1]),
)
# Folga de 2 p.p. (pontos percentuais) em volta: um eixo justo demais faz 1 p.p. parecer queda
fig.update_yaxes(range=[margens.min() - 2, margens.max() + 2], dtick=1)
mostrar(
    fig,
    completos.assign(
        Mês=[formatar_mes(m) for m in completos.mes],
        Margem=completos.margem_pecas_pct.map(formatar_pct),
    )[["Mês", "Margem"]],
)

# ---- Margem por categoria ----
secao("Margem por categoria")
categorias = itens.groupby("categoria", as_index=False).agg(
    receita=("receita", "sum"), custo=("custo_total", "sum")
)
categorias["margem_pct"] = (categorias.receita - categorias.custo) / categorias.receita
categorias["participacao"] = categorias.receita / categorias.receita.sum()
categorias = categorias.sort_values("margem_pct", ascending=False)
mostrar(
    barras_horizontais(
        categorias.categoria.tolist(),
        (categorias.margem_pct * 100).tolist(),
        "Margem",
        formato="%{x:,.1f}%",
        textos=[formatar_pct(m) for m in categorias.margem_pct],
    ),
    categorias.assign(
        Categoria=categorias.categoria,
        Receita=categorias.receita.map(formatar_moeda),
        Margem=categorias.margem_pct.map(formatar_pct),
        **{"% da receita": categorias.participacao.map(formatar_pct)},
    )[["Categoria", "Receita", "% da receita", "Margem"]],
)
maior = categorias.sort_values("receita", ascending=False).iloc[0]
st.caption(
    f"{maior.categoria} responde por {formatar_pct(maior.participacao, 0)} da receita com margem "
    f"de {formatar_pct(maior.margem_pct, 0)}. Revisar preço ou fornecedor dessa categoria "
    "mexe mais no lucro do que qualquer outra."
)

# ---- Descontos (sempre 12 meses) ----
secao(
    "Descontos no balcão",
    "Últimos 12 meses. Na oficina o sistema não registra desconto, por isso ela fica de fora.",
)
desconto = calcular("resumo_descontos", resumo_descontos)
col1, col2 = st.columns(2)
col1.metric(
    "Desconto dado",
    formatar_moeda_curta(desconto["valor_desconto"]),
    border=True,
    help="Diferença entre o preço de tabela e o preço cobrado, somada em 12 meses.",
)
col2.metric(
    "Pedidos com desconto",
    formatar_pct(desconto["pedidos_com_desconto_pct"], 0),
    border=True,
)
por_perfil = consultar("SELECT * FROM analise.descontos_por_perfil ORDER BY perfil")
mostrar(
    barras_horizontais(
        por_perfil.perfil.tolist(),
        (por_perfil.pedidos_com_desconto_pct * 100).tolist(),
        "Pedidos com desconto",
        formato="%{x:.0f}%",
        textos=[formatar_pct(v, 0) for v in por_perfil.pedidos_com_desconto_pct],
    ),
    por_perfil.assign(
        Perfil=por_perfil.perfil,
        Pedidos=por_perfil.qtd_pedidos.map(formatar_numero),
        **{
            "Com desconto": por_perfil.pedidos_com_desconto_pct.map(formatar_pct),
            "Desconto dado": por_perfil.valor_desconto.map(formatar_moeda),
            "Ticket com desconto": por_perfil.ticket_com_desconto.map(formatar_moeda),
            "Ticket sem desconto": por_perfil.ticket_sem_desconto.map(formatar_moeda),
        },
    )[
        [
            "Perfil",
            "Pedidos",
            "Com desconto",
            "Desconto dado",
            "Ticket com desconto",
            "Ticket sem desconto",
        ]
    ],
)
st.caption(
    "A mesma fatia de pedidos recebe desconto em todo tipo de cliente, e o pedido com desconto "
    f"não é maior ({formatar_moeda(desconto['ticket_com_desconto'])} contra "
    f"{formatar_moeda(desconto['ticket_sem_desconto'])}). Ou seja: o desconto não segue critério "
    "e não está comprando venda maior. Uma regra simples (só no PIX, ou só acima de um valor) "
    "devolve parte desse dinheiro."
)

# ---- Formas de pagamento (sempre 12 meses) ----
secao(
    "Quanto custa receber",
    "Últimos 12 meses, balcão + oficina. As taxas são estimativas: troque pelas do contrato.",
)
recebimentos = consultar("SELECT * FROM analise.recebimentos")
pagamento = calcular("resumo_recebimentos", resumo_recebimentos)
col1, col2 = st.columns(2)
col1.metric(
    "Custo estimado das taxas",
    formatar_moeda_curta(pagamento["custo_total"]),
    border=True,
    help="Maquininha (débito e crédito) e tarifa de boleto, pelas premissas da tabela.",
)
col2.metric(
    "Só o cartão de crédito",
    formatar_moeda_curta(pagamento["custo_credito"]),
    f"{formatar_pct(pagamento['participacao_credito'], 0)} do faturamento",
    delta_color="off",
    delta_arrow="off",
    border=True,
)
mostrar(
    barras_horizontais(
        recebimentos.forma_pagamento.tolist(),
        (recebimentos.participacao * 100).tolist(),
        "Participação no faturamento",
        formato="%{x:.0f}%",
        textos=[
            f"{formatar_pct(p, 0)} · taxa {formatar_moeda_curta(c)}"
            for p, c in zip(recebimentos.participacao, recebimentos.custo_estimado, strict=True)
        ],
    ),
    recebimentos.assign(
        Forma=recebimentos.forma_pagamento,
        Documentos=recebimentos.qtd_documentos.map(formatar_numero),
        Faturamento=recebimentos.faturamento.map(formatar_moeda),
        **{
            "% do faturamento": recebimentos.participacao.map(formatar_pct),
            "Taxa (premissa)": [
                formatar_moeda(f) + " por boleto" if f else formatar_pct(p)
                for p, f in zip(recebimentos.taxa_pct, recebimentos.taxa_fixa, strict=True)
            ],
            "Custo estimado": recebimentos.custo_estimado.map(formatar_moeda),
        },
    )[
        [
            "Forma",
            "Documentos",
            "Faturamento",
            "% do faturamento",
            "Taxa (premissa)",
            "Custo estimado",
        ]
    ],
)

# ---- Sazonalidade ----
secao("Pneus: efeito da época de chuva")
pneus = consultar("""
    SELECT month(data) AS mes, sum(receita) / count(DISTINCT date_trunc('month', data)) AS media
    FROM analise.itens_vendidos
    WHERE categoria = 'Pneus e câmaras'
    GROUP BY 1 ORDER BY 1
""")
chuva = pneus.mes.isin([11, 12, 1, 2, 3])
fig = barras_horizontais(
    [MESES_ABREV[m - 1] for m in pneus.mes],
    pneus.media.tolist(),
    "Média mensal",
    textos=[formatar_moeda_curta(v) for v in pneus.media],
    cores=[SERIES[0] if c else NEUTRO for c in chuva],
)
mostrar(
    fig,
    pneus.assign(
        Mês=[MESES_ABREV[m - 1] for m in pneus.mes],
        Época=chuva.map({True: "Chuva", False: "Seca"}),
        **{"Receita média": pneus.media.map(formatar_moeda)},
    )[["Mês", "Época", "Receita média"]],
)
fator = pneus.media[chuva].mean() / pneus.media[~chuva].mean() - 1
st.caption(
    f"Em azul, a época de chuva (nov a mar): a venda de pneus sobe {formatar_pct(fator, 0)} em "
    "relação à seca. Vale reforçar o estoque de pneus a partir de outubro."
)
