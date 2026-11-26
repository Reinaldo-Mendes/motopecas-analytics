-- 03_base_analitica.sql
-- Views (consultas salvas, recalculadas a cada leitura) que o dashboard e o bot consomem.
-- Regra de faturamento: balcão entra sempre; oficina só OS "Concluída", na data de abertura.

CREATE SCHEMA IF NOT EXISTS analise;

-- Uma linha por peça vendida, venha do balcão ou da oficina.
CREATE OR REPLACE VIEW analise.itens_vendidos AS
SELECT
    'Balcão' AS origem,
    v.numero_pedido AS numero_documento,
    v.data,
    u.id_cliente_unificado AS id_cliente,  -- NULL = consumidor final sem cadastro
    v.sku,
    p.descricao,
    p.categoria,
    v.quantidade,
    v.preco_unitario,
    v.quantidade * v.preco_unitario AS receita,
    v.quantidade * p.custo AS custo_total,
    v.forma_pagamento
FROM limpo.vendas AS v
JOIN limpo.produtos AS p USING (sku)
LEFT JOIN limpo.clientes_unificados AS u USING (id_cliente)

UNION ALL

SELECT
    'Oficina',
    o.numero_os,
    o.data_abertura,
    u.id_cliente_unificado,
    i.sku,
    p.descricao,
    p.categoria,
    i.quantidade,
    i.preco_unitario,
    i.quantidade * i.preco_unitario,
    i.quantidade * p.custo,
    o.forma_pagamento
FROM limpo.itens_os AS i
JOIN limpo.ordens_servico AS o USING (numero_os)
JOIN limpo.produtos AS p USING (sku)
LEFT JOIN limpo.clientes_unificados AS u ON u.id_cliente = o.id_cliente
WHERE o.status = 'Concluída';


-- Ordens de serviço concluídas com o total de peças e de mão de obra.
CREATE OR REPLACE VIEW analise.ordens_concluidas AS
WITH pecas AS (
    SELECT numero_os, sum(quantidade * preco_unitario) AS valor_pecas
    FROM limpo.itens_os
    GROUP BY numero_os
)
SELECT
    o.numero_os,
    o.data_abertura,
    o.data_conclusao,
    o.data_conclusao - o.data_abertura AS dias_na_oficina,
    u.id_cliente_unificado AS id_cliente,
    o.moto,
    o.placa,
    o.servico,
    o.mecanico,
    o.valor_mao_obra,
    coalesce(p.valor_pecas, 0) AS valor_pecas,
    o.valor_mao_obra + coalesce(p.valor_pecas, 0) AS valor_total
FROM limpo.ordens_servico AS o
LEFT JOIN pecas AS p USING (numero_os)
LEFT JOIN limpo.clientes_unificados AS u ON u.id_cliente = o.id_cliente
WHERE o.status = 'Concluída';


-- "Hoje" das análises = último dia com movimento nos dados (e não current_date). Assim os
-- números não mudam conforme o dia em que alguém abre o dashboard.
-- Considera também OS só de mão de obra (sem peça), que não aparecem em itens_vendidos.
CREATE OR REPLACE VIEW analise.referencia AS
WITH movimento AS (
    SELECT data FROM analise.itens_vendidos
    UNION ALL
    SELECT data_abertura FROM analise.ordens_concluidas
)
SELECT
    max(data) AS data_referencia,
    min(data) AS data_inicial
FROM movimento;


-- Relatório "antes x depois" da limpeza: mostra ao cliente o que havia de errado nos dados.
CREATE OR REPLACE VIEW analise.qualidade_dados AS
SELECT * FROM (VALUES
    ('Datas fora do padrão ISO (aaaa-mm-dd)',
        (SELECT count(*) FROM bruto.vendas WHERE NOT regexp_full_match(data, '\d{4}-\d{2}-\d{2}'))
      + (SELECT count(*) FROM bruto.ordens_servico
         WHERE NOT regexp_full_match(data_abertura, '\d{4}-\d{2}-\d{2}'))),
    ('Datas que não foi possível interpretar',
        (SELECT count(*) FROM limpo.vendas WHERE data IS NULL)
      + (SELECT count(*) FROM limpo.ordens_servico WHERE data_abertura IS NULL)),
    ('Clientes sem telefone válido',
        (SELECT count(*) FROM limpo.clientes_consolidados WHERE telefone IS NULL)),
    ('Cadastros de cliente duplicados unificados',
        (SELECT count(*) FROM limpo.clientes_unificados WHERE id_cliente <> id_cliente_unificado)),
    ('Itens vendidos com preço zerado (corrigidos)',
        (SELECT count(*) FROM limpo.vendas WHERE preco_corrigido)
      + (SELECT count(*) FROM limpo.itens_os WHERE preco_corrigido)),
    ('Produtos sem preço de venda no cadastro',
        (SELECT count(*) FROM limpo.produtos WHERE preco_pendente)),
    ('OS canceladas (fora do faturamento)',
        (SELECT count(*) FROM limpo.ordens_servico WHERE status = 'Cancelada'))
) AS t(problema, quantidade);
