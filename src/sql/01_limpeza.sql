-- 01_limpeza.sql
-- Converte os textos brutos do ERP (schema `bruto`, tudo VARCHAR) em tabelas tipadas e
-- padronizadas no schema `limpo`. Nenhuma linha é descartada: o que não dá para corrigir
-- fica NULL e é sinalizado, para aparecer no relatório de qualidade.

CREATE SCHEMA IF NOT EXISTS limpo;

-- Macros são funções SQL reutilizáveis (parecido com um método estático utilitário em Java).

-- Datas chegam em 4 formatos. Escolhemos o formato pelo padrão do texto, em vez de "tentar
-- todos", porque '27/11/24' com '%d/%m/%Y' viraria o ano 24 d.C.
CREATE OR REPLACE MACRO para_data(texto) AS
    CASE
        WHEN regexp_full_match(texto, '\d{2}/\d{2}/\d{4}') THEN strptime(texto, '%d/%m/%Y')::DATE
        WHEN regexp_full_match(texto, '\d{4}-\d{2}-\d{2}') THEN strptime(texto, '%Y-%m-%d')::DATE
        WHEN regexp_full_match(texto, '\d{2}/\d{2}/\d{2}') THEN strptime(texto, '%d/%m/%y')::DATE
        WHEN regexp_full_match(texto, '\d{2}-\d{2}-\d{4}') THEN strptime(texto, '%d-%m-%Y')::DATE
    END;

-- 'R$ 1.234,56' ou '1234,56' -> 1234.56
CREATE OR REPLACE MACRO para_decimal(texto) AS
    TRY_CAST(
        replace(replace(trim(replace(texto, 'R$', '')), '.', ''), ',', '.')
        AS DECIMAL(12, 2)
    );

-- Telefone só com dígitos, sempre com DDD. Celular sem DDD (9 dígitos) recebe o DDD da
-- cidade (35). Qualquer outra coisa vira NULL.
CREATE OR REPLACE MACRO limpar_telefone(texto) AS
    CASE length(regexp_replace(texto, '\D', '', 'g'))
        WHEN 11 THEN regexp_replace(texto, '\D', '', 'g')
        WHEN 9 THEN '35' || regexp_replace(texto, '\D', '', 'g')
    END;

-- 'JOSÉ  da Silva ' -> 'jose da silva' (chave para comparar nomes)
CREATE OR REPLACE MACRO normalizar_nome(texto) AS
    lower(strip_accents(regexp_replace(trim(texto), '\s+', ' ', 'g')));


-- Produtos ------------------------------------------------------------------------------
-- Preço de venda zerado = cadastro incompleto: vira NULL e é sinalizado.
CREATE OR REPLACE TABLE limpo.produtos AS
SELECT
    sku,
    descricao,
    categoria,
    marca,
    compatibilidade,
    para_decimal(custo) AS custo,
    nullif(para_decimal(preco_venda), 0) AS preco_venda,
    coalesce(para_decimal(preco_venda), 0) = 0 AS preco_pendente,
    estoque_atual::INTEGER AS estoque_atual,
    estoque_minimo::INTEGER AS estoque_minimo,
    para_data(data_cadastro) AS data_cadastro
FROM bruto.produtos;


-- Clientes ------------------------------------------------------------------------------
CREATE OR REPLACE TABLE limpo.clientes AS
SELECT
    id_cliente::INTEGER AS id_cliente,
    regexp_replace(trim(nome), '\s+', ' ', 'g') AS nome,
    normalizar_nome(nome) AS nome_normalizado,
    nullif(regexp_replace(cpf_cnpj, '\D', '', 'g'), '') AS documento,  -- CPF ou CNPJ só dígitos
    tipo_pessoa,
    limpar_telefone(telefone) AS telefone,
    lower(email) AS email,
    cidade,
    uf,
    para_data(data_cadastro) AS data_cadastro
FROM bruto.clientes;


-- Vendas do balcão ----------------------------------------------------------------------
-- Preço unitário zerado é corrigido, em ordem de confiança:
--   1) preço mais comum do mesmo SKU com o mesmo desconto em outras vendas;
--   2) preço de tabela do cadastro com o desconto aplicado.
CREATE OR REPLACE TABLE limpo.vendas AS
WITH base AS (
    SELECT
        numero_pedido::INTEGER AS numero_pedido,
        para_data(data) AS data,
        id_cliente::INTEGER AS id_cliente,
        sku,
        quantidade::INTEGER AS quantidade,
        para_decimal(preco_unitario) AS preco_informado,
        para_decimal(desconto_pct) AS desconto_pct,
        forma_pagamento
    FROM bruto.vendas
),
preco_tipico AS (
    SELECT sku, desconto_pct, mode(preco_informado) AS preco
    FROM base
    WHERE preco_informado > 0
    GROUP BY sku, desconto_pct
)
SELECT
    b.numero_pedido,
    b.data,
    b.id_cliente,
    b.sku,
    b.quantidade,
    coalesce(
        nullif(b.preco_informado, 0),
        t.preco,
        round(p.preco_venda * (1 - b.desconto_pct), 2)
    )::DECIMAL(12, 2) AS preco_unitario,
    coalesce(b.preco_informado, 0) = 0 AS preco_corrigido,
    b.desconto_pct,
    b.forma_pagamento
FROM base AS b
LEFT JOIN preco_tipico AS t USING (sku, desconto_pct)
LEFT JOIN limpo.produtos AS p USING (sku);


-- Ordens de serviço ---------------------------------------------------------------------
CREATE OR REPLACE TABLE limpo.ordens_servico AS
SELECT
    numero_os::INTEGER AS numero_os,
    para_data(data_abertura) AS data_abertura,
    para_data(data_conclusao) AS data_conclusao,
    status,
    id_cliente::INTEGER AS id_cliente,
    moto,
    upper(replace(placa, '-', '')) AS placa,
    servico,
    mecanico,
    para_decimal(valor_mao_obra) AS valor_mao_obra,
    forma_pagamento
FROM bruto.ordens_servico;


-- Peças usadas nas OS ---------------------------------------------------------------------
-- Correção de preço zerado: preço mais comum do SKU para o mesmo cliente (frota tem
-- desconto próprio), depois preço mais comum do SKU na oficina, depois preço de tabela.
CREATE OR REPLACE TABLE limpo.itens_os AS
WITH base AS (
    SELECT
        i.numero_os::INTEGER AS numero_os,
        i.sku,
        i.quantidade::INTEGER AS quantidade,
        para_decimal(i.preco_unitario) AS preco_informado,
        o.id_cliente
    FROM bruto.itens_os AS i
    JOIN limpo.ordens_servico AS o ON o.numero_os = i.numero_os::INTEGER
),
preco_cliente AS (
    SELECT id_cliente, sku, mode(preco_informado) AS preco
    FROM base WHERE preco_informado > 0
    GROUP BY id_cliente, sku
),
preco_oficina AS (
    SELECT sku, mode(preco_informado) AS preco
    FROM base WHERE preco_informado > 0
    GROUP BY sku
)
SELECT
    b.numero_os,
    b.sku,
    b.quantidade,
    coalesce(nullif(b.preco_informado, 0), pc.preco, po.preco, p.preco_venda)::DECIMAL(12, 2)
        AS preco_unitario,
    coalesce(b.preco_informado, 0) = 0 AS preco_corrigido
FROM base AS b
LEFT JOIN preco_cliente AS pc USING (id_cliente, sku)
LEFT JOIN preco_oficina AS po USING (sku)
LEFT JOIN limpo.produtos AS p USING (sku);
