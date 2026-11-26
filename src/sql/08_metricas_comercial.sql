-- 08_metricas_comercial.sql
-- Descontos do balcão e custo de cada forma de pagamento.

-- Um pedido de balcão por linha, com o desconto em reais. O ERP grava o preço JÁ com
-- desconto, então o preço cheio é reconstruído: preço / (1 - desconto).
-- (Na oficina o ERP não registra desconto, por isso ela fica de fora.)
CREATE OR REPLACE VIEW analise.pedidos_desconto AS
SELECT
    v.numero_pedido,
    v.data,
    u.id_cliente_unificado AS id_cliente,
    max(v.desconto_pct) AS desconto_pct,
    sum(v.quantidade * v.preco_unitario) AS receita,
    sum(v.quantidade * v.preco_unitario / (1 - v.desconto_pct)) AS receita_sem_desconto,
    sum(v.quantidade * v.preco_unitario / (1 - v.desconto_pct))
        - sum(v.quantidade * v.preco_unitario) AS valor_desconto
FROM limpo.vendas AS v
LEFT JOIN limpo.clientes_unificados AS u USING (id_cliente)
GROUP BY v.numero_pedido, v.data, u.id_cliente_unificado;


-- Descontos por mês: quanto se deu e quanto isso pesa na margem das peças do balcão.
CREATE OR REPLACE VIEW analise.descontos_mensais AS
WITH margem AS (
    SELECT date_trunc('month', data)::DATE AS mes, sum(receita - custo_total) AS margem_balcao
    FROM analise.itens_vendidos
    WHERE origem = 'Balcão'
    GROUP BY 1
),
descontos AS (
    SELECT
        date_trunc('month', data)::DATE AS mes,
        count(*) AS qtd_pedidos,
        count(*) FILTER (WHERE desconto_pct > 0) AS qtd_com_desconto,
        sum(valor_desconto) AS valor_desconto
    FROM analise.pedidos_desconto
    GROUP BY 1
)
SELECT
    d.*,
    m.margem_balcao,
    d.valor_desconto / nullif(m.margem_balcao, 0) AS desconto_sobre_margem
FROM descontos AS d
LEFT JOIN margem AS m USING (mes)
ORDER BY d.mes;


-- Quem recebe desconto (últimos 12 meses): consumidor sem cadastro ou cada perfil de cliente.
-- Se a taxa é parecida em todos os grupos, o desconto não segue critério nenhum.
CREATE OR REPLACE VIEW analise.descontos_por_perfil AS
SELECT
    coalesce(c.perfil, 'Sem cadastro') AS perfil,
    count(*) AS qtd_pedidos,
    avg((d.desconto_pct > 0)::INTEGER) AS pedidos_com_desconto_pct,
    sum(d.valor_desconto) AS valor_desconto,
    avg(d.receita) FILTER (WHERE d.desconto_pct > 0) AS ticket_com_desconto,
    avg(d.receita) FILTER (WHERE d.desconto_pct = 0) AS ticket_sem_desconto
FROM analise.pedidos_desconto AS d
LEFT JOIN analise.clientes_perfil AS c USING (id_cliente)
CROSS JOIN analise.referencia AS r
WHERE d.data > r.data_referencia - 365
GROUP BY 1
ORDER BY valor_desconto DESC;


-- Taxas de recebimento. São PREMISSAS (valores típicos de maquininha e banco), não vêm do
-- ERP: troque pelos números do contrato da loja.
CREATE OR REPLACE VIEW analise.premissas_pagamento AS
SELECT * FROM (VALUES
    ('PIX', 0.0, 0.00),
    ('Dinheiro', 0.0, 0.00),
    ('Cartão de débito', 0.014, 0.00),
    ('Cartão de crédito', 0.032, 0.00),
    ('Boleto 28 dias', 0.0, 3.50)
) AS t(forma_pagamento, taxa_pct, taxa_fixa);


-- Faturamento e custo estimado de cada forma de pagamento nos últimos 12 meses.
-- Documento = um pedido de balcão ou uma OS concluída (cada um é pago de uma vez).
CREATE OR REPLACE VIEW analise.recebimentos AS
WITH documentos AS (
    SELECT
        numero_pedido AS documento,
        data,
        forma_pagamento,
        sum(quantidade * preco_unitario) AS valor
    FROM limpo.vendas
    GROUP BY numero_pedido, data, forma_pagamento
    UNION ALL
    SELECT o.numero_os, o.data_abertura, s.forma_pagamento, o.valor_total
    FROM analise.ordens_concluidas AS o
    JOIN limpo.ordens_servico AS s USING (numero_os)
),
por_forma AS (
    SELECT
        d.forma_pagamento,
        count(*) AS qtd_documentos,
        sum(d.valor) AS faturamento,
        sum(d.valor * p.taxa_pct + p.taxa_fixa) AS custo_estimado
    FROM documentos AS d
    JOIN analise.premissas_pagamento AS p USING (forma_pagamento)
    CROSS JOIN analise.referencia AS r
    WHERE d.data > r.data_referencia - 365
    GROUP BY d.forma_pagamento
)
SELECT
    f.*,
    f.faturamento / sum(f.faturamento) OVER () AS participacao,
    f.custo_estimado / f.faturamento AS custo_pct,
    p.taxa_pct,
    p.taxa_fixa
FROM por_forma AS f
JOIN analise.premissas_pagamento AS p USING (forma_pagamento)
ORDER BY f.faturamento DESC;
