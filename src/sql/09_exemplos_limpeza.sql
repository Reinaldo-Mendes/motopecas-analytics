-- 09_exemplos_limpeza.sql
-- Exemplos de "antes x depois" para a página de dados brutos: o valor como veio do ERP ao lado
-- do valor depois da limpeza. Um exemplo por tipo de problema, sempre a primeira ocorrência
-- (assim a página mostra sempre as mesmas linhas).

-- Datas: um exemplo de cada um dos formatos que aparecem nas vendas.
CREATE OR REPLACE VIEW analise.exemplo_datas AS
WITH base AS (
    SELECT
        CASE
            WHEN regexp_full_match(b.data, '\d{2}/\d{2}/\d{4}') THEN 'dd/mm/aaaa'
            WHEN regexp_full_match(b.data, '\d{4}-\d{2}-\d{2}') THEN 'aaaa-mm-dd'
            WHEN regexp_full_match(b.data, '\d{2}/\d{2}/\d{2}') THEN 'dd/mm/aa'
            WHEN regexp_full_match(b.data, '\d{2}-\d{2}-\d{4}') THEN 'dd-mm-aaaa'
            ELSE 'outro'
        END AS formato,
        b.data AS valor_bruto,
        l.data AS valor_limpo,
        l.numero_pedido
    FROM bruto.vendas AS b
    JOIN limpo.vendas AS l ON l.numero_pedido = b.numero_pedido::INTEGER AND l.sku = b.sku
)
SELECT
    formato,
    count(*) OVER (PARTITION BY formato) AS qtd_linhas,
    valor_bruto,
    valor_limpo
FROM base
QUALIFY row_number() OVER (PARTITION BY formato ORDER BY numero_pedido) = 1
ORDER BY qtd_linhas DESC;


-- Telefones: um exemplo de cada padrão (9 = dígito) e o resultado padronizado.
CREATE OR REPLACE VIEW analise.exemplo_telefones AS
WITH base AS (
    SELECT
        CASE
            WHEN coalesce(trim(b.telefone), '') = '' THEN '(vazio)'
            ELSE regexp_replace(b.telefone, '\d', '9', 'g')
        END AS padrao,
        b.telefone AS valor_bruto,
        l.telefone AS valor_limpo,
        l.id_cliente
    FROM bruto.clientes AS b
    JOIN limpo.clientes AS l ON l.id_cliente = b.id_cliente::INTEGER
)
SELECT
    padrao,
    count(*) OVER (PARTITION BY padrao) AS qtd_clientes,
    valor_bruto,
    valor_limpo
FROM base
QUALIFY row_number() OVER (PARTITION BY padrao ORDER BY id_cliente) = 1
ORDER BY qtd_clientes DESC;


-- Cadastros duplicados: um grupo de exemplo para cada motivo de unificação, com os cadastros
-- exatamente como vieram do ERP.
CREATE OR REPLACE VIEW analise.exemplo_duplicados AS
WITH grupos AS (
    SELECT
        id_cliente_unificado,
        any_value(motivo_unificacao) FILTER (WHERE id_cliente <> id_cliente_unificado) AS motivo
    FROM limpo.clientes_unificados
    GROUP BY id_cliente_unificado
    HAVING count(*) > 1
),
escolhidos AS (
    SELECT *
    FROM grupos
    QUALIFY row_number() OVER (PARTITION BY motivo ORDER BY id_cliente_unificado) = 1
)
SELECT
    e.motivo,
    u.id_cliente_unificado,
    b.id_cliente::INTEGER AS id_cliente,
    b.nome,
    b.cpf_cnpj,
    b.telefone,
    b.data_cadastro
FROM escolhidos AS e
JOIN limpo.clientes_unificados AS u USING (id_cliente_unificado)
JOIN bruto.clientes AS b ON b.id_cliente::INTEGER = u.id_cliente
ORDER BY e.motivo, u.id_cliente_unificado, id_cliente;


-- Preços zerados nas vendas e o preço que a limpeza colocou no lugar.
CREATE OR REPLACE VIEW analise.exemplo_precos AS
SELECT
    l.numero_pedido,
    l.sku,
    p.descricao,
    b.preco_unitario AS valor_bruto,
    b.desconto_pct AS desconto_bruto,
    l.preco_unitario AS valor_limpo
FROM bruto.vendas AS b
JOIN limpo.vendas AS l ON l.numero_pedido = b.numero_pedido::INTEGER AND l.sku = b.sku
JOIN limpo.produtos AS p ON p.sku = l.sku
WHERE l.preco_corrigido
ORDER BY l.numero_pedido, l.sku;
