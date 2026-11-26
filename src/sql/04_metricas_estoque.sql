-- 04_metricas_estoque.sql
-- Uma linha por SKU com giro, curva ABC e a situação do item no estoque.
--
-- Curva ABC (pela receita dos últimos 12 meses, do maior para o menor):
--   A = itens que, somados, formam os primeiros 80% da receita;
--   B = os próximos 15% (até 95%);  C = o restante, incluindo quem não vendeu.
-- Situação:
--   Sem giro  = tem estoque e não sai há 180+ dias (dinheiro parado na prateleira);
--   Em falta  = estoque zerado, mas vendeu nos últimos 90 dias (venda perdida);
--   Repor     = estoque abaixo do mínimo cadastrado, e com saída recente;
--   Ok        = o resto.

CREATE OR REPLACE VIEW analise.estoque AS
WITH ref AS (
    SELECT data_referencia FROM analise.referencia
),
saidas AS (
    SELECT
        i.sku,
        max(i.data) AS ultima_saida,
        sum(i.quantidade) FILTER (WHERE i.data > r.data_referencia - 90) AS qtd_90d,
        sum(i.receita) FILTER (WHERE i.data > r.data_referencia - 365) AS receita_12m,
        sum(i.receita - i.custo_total) FILTER (WHERE i.data > r.data_referencia - 365)
            AS margem_12m
    FROM analise.itens_vendidos AS i
    CROSS JOIN ref AS r
    GROUP BY i.sku
),
base AS (
    SELECT
        p.*,
        s.ultima_saida,
        r.data_referencia - coalesce(s.ultima_saida, p.data_cadastro) AS dias_sem_venda,
        coalesce(s.qtd_90d, 0) AS qtd_vendida_90d,
        coalesce(s.receita_12m, 0) AS receita_12m,
        coalesce(s.margem_12m, 0) AS margem_12m
    FROM limpo.produtos AS p
    LEFT JOIN saidas AS s USING (sku)
    CROSS JOIN ref AS r
),
abc AS (
    SELECT
        *,
        -- receita acumulada ANTES deste item (quem cruza a linha dos 80% ainda é A)
        sum(receita_12m) OVER (ORDER BY receita_12m DESC, sku ROWS UNBOUNDED PRECEDING)
            - receita_12m AS acumulado_antes,
        sum(receita_12m) OVER () AS receita_total
    FROM base
)
SELECT
    sku,
    descricao,
    categoria,
    marca,
    compatibilidade,
    custo,
    preco_venda,
    estoque_atual,
    estoque_minimo,
    estoque_atual * custo AS valor_estoque,  -- a preço de custo
    ultima_saida,
    dias_sem_venda,
    qtd_vendida_90d,
    CASE WHEN qtd_vendida_90d > 0 THEN round(estoque_atual / (qtd_vendida_90d / 90.0)) END
        AS cobertura_dias,  -- quantos dias o estoque dura no ritmo atual
    receita_12m,
    margem_12m,
    CASE
        WHEN receita_12m = 0 THEN 'C'
        WHEN acumulado_antes < 0.80 * receita_total THEN 'A'
        WHEN acumulado_antes < 0.95 * receita_total THEN 'B'
        ELSE 'C'
    END AS classe_abc,
    CASE
        WHEN estoque_atual > 0 AND dias_sem_venda >= 180 THEN 'Sem giro'
        WHEN estoque_atual = 0 AND qtd_vendida_90d > 0 THEN 'Em falta'
        WHEN estoque_atual < estoque_minimo AND qtd_vendida_90d > 0 THEN 'Repor'
        ELSE 'Ok'
    END AS situacao
FROM abc;
