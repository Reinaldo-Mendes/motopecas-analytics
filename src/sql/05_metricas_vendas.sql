-- 05_metricas_vendas.sql
-- Faturamento e margem. Margem aqui é a margem bruta das peças (preço de venda - custo);
-- a mão de obra entra inteira no lucro bruto, porque o ERP não registra o custo do mecânico.

CREATE OR REPLACE VIEW analise.faturamento_mensal AS
WITH pecas AS (
    SELECT
        date_trunc('month', data)::DATE AS mes,
        sum(receita) FILTER (WHERE origem = 'Balcão') AS pecas_balcao,
        sum(receita) FILTER (WHERE origem = 'Oficina') AS pecas_oficina,
        sum(custo_total) AS custo_pecas
    FROM analise.itens_vendidos
    GROUP BY 1
),
mao_de_obra AS (
    SELECT
        date_trunc('month', data_abertura)::DATE AS mes,
        sum(valor_mao_obra) AS mao_de_obra,
        count(*) AS qtd_os
    FROM analise.ordens_concluidas
    GROUP BY 1
),
pedidos AS (
    SELECT date_trunc('month', data)::DATE AS mes, count(DISTINCT numero_pedido) AS qtd_pedidos
    FROM limpo.vendas
    GROUP BY 1
),
-- Meses com qualquer movimento: um mês só com mão de obra (sem peça) também conta
meses AS (
    SELECT mes FROM pecas
    UNION
    SELECT mes FROM mao_de_obra
),
valores AS (
    SELECT
        meses.mes,
        coalesce(p.pecas_balcao, 0) AS pecas_balcao,
        coalesce(p.pecas_oficina, 0) AS pecas_oficina,
        coalesce(m.mao_de_obra, 0) AS mao_de_obra,
        coalesce(p.custo_pecas, 0) AS custo_pecas,
        coalesce(d.qtd_pedidos, 0) AS qtd_pedidos,
        coalesce(m.qtd_os, 0) AS qtd_os
    FROM meses
    LEFT JOIN pecas AS p USING (mes)
    LEFT JOIN mao_de_obra AS m USING (mes)
    LEFT JOIN pedidos AS d USING (mes)
)
SELECT
    v.mes,
    v.pecas_balcao,
    v.pecas_oficina,
    v.mao_de_obra,
    v.pecas_balcao + v.pecas_oficina + v.mao_de_obra AS faturamento,
    v.custo_pecas,
    v.pecas_balcao + v.pecas_oficina - v.custo_pecas AS margem_pecas,
    (v.pecas_balcao + v.pecas_oficina - v.custo_pecas)
        / nullif(v.pecas_balcao + v.pecas_oficina, 0) AS margem_pecas_pct,
    v.pecas_balcao + v.pecas_oficina + v.mao_de_obra - v.custo_pecas AS lucro_bruto,
    v.qtd_pedidos,
    v.qtd_os,
    -- primeiro e último mês costumam estar pela metade: o gráfico deve sinalizar
    v.mes >= r.data_inicial AND last_day(v.mes) <= r.data_referencia AS mes_completo
FROM valores AS v
CROSS JOIN analise.referencia AS r
ORDER BY v.mes;


-- Margem por categoria nos últimos 12 meses (balcão + oficina).
CREATE OR REPLACE VIEW analise.margem_categoria AS
SELECT
    i.categoria,
    sum(i.receita) AS receita,
    sum(i.custo_total) AS custo,
    sum(i.receita - i.custo_total) AS margem,
    sum(i.receita - i.custo_total) / sum(i.receita) AS margem_pct,
    sum(i.receita) / sum(sum(i.receita)) OVER () AS participacao_receita
FROM analise.itens_vendidos AS i
CROSS JOIN analise.referencia AS r
WHERE i.data > r.data_referencia - 365
GROUP BY i.categoria
ORDER BY receita DESC;
