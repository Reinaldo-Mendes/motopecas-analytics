-- 06_metricas_oficina.sql
-- Produção da oficina por mecânico e desempenho de cada tipo de serviço.

CREATE OR REPLACE VIEW analise.oficina_mecanicos AS
SELECT
    date_trunc('month', data_abertura)::DATE AS mes,
    mecanico,
    count(*) AS qtd_os,
    sum(valor_mao_obra) AS mao_de_obra,
    sum(valor_total) AS valor_total,
    avg(dias_na_oficina) AS dias_medios_na_oficina
FROM analise.ordens_concluidas
GROUP BY ALL
ORDER BY mes, mecanico;


-- Últimos 12 meses por serviço: volume, ticket médio e quanto vem de peça x mão de obra.
CREATE OR REPLACE VIEW analise.oficina_servicos AS
SELECT
    o.servico,
    count(*) AS qtd_os,
    avg(o.valor_total) AS ticket_medio,
    avg(o.valor_mao_obra) AS mao_de_obra_media,
    avg(o.valor_pecas) AS pecas_media,
    sum(o.valor_total) AS valor_total,
    avg(o.dias_na_oficina) AS dias_medios_na_oficina
FROM analise.ordens_concluidas AS o
CROSS JOIN analise.referencia AS r
WHERE o.data_abertura > r.data_referencia - 365
GROUP BY o.servico
ORDER BY qtd_os DESC;


-- Todas as OS (inclusive canceladas e em andamento) com o valor orçado: mão de obra + peças.
-- Para OS cancelada o "orçamento" é o que teria sido faturado se o cliente aprovasse.
CREATE OR REPLACE VIEW analise.orcamentos_os AS
WITH pecas AS (
    SELECT numero_os, sum(quantidade * preco_unitario) AS valor_pecas
    FROM limpo.itens_os
    GROUP BY numero_os
)
SELECT
    o.numero_os,
    o.data_abertura,
    o.status,
    o.servico,
    o.mecanico,
    o.moto,
    o.valor_mao_obra + coalesce(p.valor_pecas, 0) AS valor_orcamento,
    CASE
        WHEN o.valor_mao_obra + coalesce(p.valor_pecas, 0) <= 150 THEN '1. Até R$ 150'
        WHEN o.valor_mao_obra + coalesce(p.valor_pecas, 0) <= 300 THEN '2. R$ 150 a 300'
        WHEN o.valor_mao_obra + coalesce(p.valor_pecas, 0) <= 500 THEN '3. R$ 300 a 500'
        ELSE '4. Acima de R$ 500'
    END AS faixa_orcamento  -- o número na frente só serve para ordenar
FROM limpo.ordens_servico AS o
LEFT JOIN pecas AS p USING (numero_os);


-- Cancelamentos dos últimos 12 meses por serviço: quanto deixou de entrar.
CREATE OR REPLACE VIEW analise.oficina_cancelamentos AS
SELECT
    o.servico,
    count(*) FILTER (WHERE o.status <> 'Em andamento') AS qtd_os,
    count(*) FILTER (WHERE o.status = 'Cancelada') AS qtd_canceladas,
    count(*) FILTER (WHERE o.status = 'Cancelada')
        / nullif(count(*) FILTER (WHERE o.status <> 'Em andamento'), 0) AS taxa_cancelamento,
    coalesce(sum(o.valor_orcamento) FILTER (WHERE o.status = 'Cancelada'), 0) AS valor_perdido,
    avg(o.valor_orcamento) AS orcamento_medio
FROM analise.orcamentos_os AS o
CROSS JOIN analise.referencia AS r
WHERE o.data_abertura > r.data_referencia - 365
GROUP BY o.servico
ORDER BY valor_perdido DESC;


-- Mesma conta por faixa de valor do orçamento: mostra se o cliente desiste quando fica caro.
CREATE OR REPLACE VIEW analise.cancelamento_por_faixa AS
SELECT
    o.faixa_orcamento,
    count(*) AS qtd_os,
    count(*) FILTER (WHERE o.status = 'Cancelada') AS qtd_canceladas,
    count(*) FILTER (WHERE o.status = 'Cancelada') / count(*) AS taxa_cancelamento,
    coalesce(sum(o.valor_orcamento) FILTER (WHERE o.status = 'Cancelada'), 0) AS valor_perdido
FROM analise.orcamentos_os AS o
CROSS JOIN analise.referencia AS r
WHERE o.data_abertura > r.data_referencia - 365 AND o.status <> 'Em andamento'
GROUP BY o.faixa_orcamento
ORDER BY o.faixa_orcamento;


-- Prazo de entrega por mecânico (últimos 12 meses). A troca de óleo fica de fora: é rápida
-- para todo mundo e esconderia a diferença nos serviços que exigem mais.
CREATE OR REPLACE VIEW analise.oficina_prazo AS
SELECT
    o.mecanico,
    count(*) AS qtd_os,
    avg(o.dias_na_oficina) AS dias_medios,
    avg((o.dias_na_oficina = 0)::INTEGER) AS entregue_no_dia_pct,
    avg((o.dias_na_oficina >= 3)::INTEGER) AS tres_dias_ou_mais_pct
FROM analise.ordens_concluidas AS o
CROSS JOIN analise.referencia AS r
WHERE o.data_abertura > r.data_referencia - 365 AND o.servico <> 'Troca de óleo'
GROUP BY o.mecanico
ORDER BY dias_medios;


-- Venda casada na oficina: em cada serviço, quantas OS levaram a peça que "combina" com ele.
-- O potencial supõe que 60% das OS levassem o item (meta usada como premissa, ajustável).
CREATE OR REPLACE VIEW analise.oficina_venda_casada AS
WITH pares(servico, item, padrao) AS (
    VALUES
        ('Troca de óleo', 'Filtro de óleo', 'Filtro de óleo%'),
        ('Troca de pneu', 'Câmara de ar', 'Câmara de ar%'),
        ('Troca de relação', 'Lubrificante de corrente', 'Lubrificante de corrente%'),
        ('Troca de pastilha/lona', 'Fluido de freio', 'Fluido de freio%'),
        ('Revisão geral', 'Vela de ignição', 'Vela de ignição%')
),
meta AS (SELECT 0.60 AS taxa_meta),
os_12m AS (
    SELECT o.numero_os, o.servico
    FROM analise.ordens_concluidas AS o
    CROSS JOIN analise.referencia AS r
    WHERE o.data_abertura > r.data_referencia - 365
),
com_item AS (
    SELECT DISTINCT os.numero_os, pr.item
    FROM os_12m AS os
    JOIN pares AS pr USING (servico)
    JOIN analise.itens_vendidos AS i
        ON i.origem = 'Oficina' AND i.numero_documento = os.numero_os
       AND i.descricao ILIKE pr.padrao
),
preco_item AS (  -- quanto o item rende em média, em receita e em margem, por unidade vendida
    SELECT
        pr.item,
        sum(i.receita) / sum(i.quantidade) AS receita_unidade,
        sum(i.receita - i.custo_total) / sum(i.quantidade) AS margem_unidade
    FROM analise.itens_vendidos AS i
    JOIN pares AS pr ON i.descricao ILIKE pr.padrao
    GROUP BY pr.item
)
SELECT
    pr.servico,
    pr.item,
    count(DISTINCT os.numero_os) AS qtd_os,
    count(DISTINCT c.numero_os) AS qtd_com_item,
    count(DISTINCT c.numero_os) / count(DISTINCT os.numero_os) AS taxa_atual,
    m.taxa_meta,
    p.receita_unidade,
    -- sem nenhuma venda do item não há preço de referência: o potencial fica 0
    greatest(m.taxa_meta * count(DISTINCT os.numero_os) - count(DISTINCT c.numero_os), 0)
        * coalesce(p.receita_unidade, 0) AS receita_potencial_12m,
    greatest(m.taxa_meta * count(DISTINCT os.numero_os) - count(DISTINCT c.numero_os), 0)
        * coalesce(p.margem_unidade, 0) AS margem_potencial_12m
FROM pares AS pr
JOIN os_12m AS os USING (servico)
LEFT JOIN com_item AS c ON c.numero_os = os.numero_os AND c.item = pr.item
LEFT JOIN preco_item AS p ON p.item = pr.item
CROSS JOIN meta AS m
GROUP BY pr.servico, pr.item, m.taxa_meta, p.receita_unidade, p.margem_unidade
ORDER BY receita_potencial_12m DESC;
