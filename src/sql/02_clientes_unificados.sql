-- 02_clientes_unificados.sql
-- O mesmo cliente às vezes foi cadastrado duas vezes, com grafias diferentes
-- ("José da Silva" x "JOSE  DA SILVA"). Aqui ligamos cada cadastro a um código único.
--
-- Dois cadastros são considerados a mesma pessoa quando, sendo do mesmo tipo (PF/PJ):
--   a) têm o mesmo CPF/CNPJ; ou
--   b) têm o mesmo telefone E o mesmo primeiro nome (evita juntar parentes que dividem o fone); ou
--   c) têm o mesmo nome normalizado, os documentos não se contradizem (um deles está vazio)
--      E o nome não é ambíguo. "Lucca Moraes" é ambíguo se existir outro "Lucca Moraes" ou um
--      "Lucca Moraes Silva": pode ser um nome digitado pela metade, então não arriscamos.
-- Variações mais drásticas ("José A. Silva" sem telefone nem CPF) não são detectadas: é um
-- critério conservador, que prefere deixar passar a juntar pessoas diferentes.
-- O código unificado é o menor id do par (o cadastro mais antigo).

CREATE OR REPLACE TABLE limpo.clientes_unificados AS
WITH nomes_ambiguos AS (
    SELECT a.id_cliente
    FROM limpo.clientes AS a
    JOIN limpo.clientes AS b
        ON b.id_cliente <> a.id_cliente
        AND b.tipo_pessoa = a.tipo_pessoa
        AND (b.nome_normalizado = a.nome_normalizado
             OR starts_with(b.nome_normalizado, a.nome_normalizado || ' '))
    GROUP BY a.id_cliente
    HAVING count(*) > 1
),
pares AS (
    SELECT
        novo.id_cliente,
        antigo.id_cliente AS id_par,
        novo.documento = antigo.documento AS por_documento,
        novo.telefone = antigo.telefone
            AND split_part(novo.nome_normalizado, ' ', 1)
              = split_part(antigo.nome_normalizado, ' ', 1) AS por_telefone,
        novo.nome_normalizado = antigo.nome_normalizado
            AND (novo.documento IS NULL OR antigo.documento IS NULL)
            AND novo.id_cliente NOT IN (SELECT id_cliente FROM nomes_ambiguos) AS por_nome
    FROM limpo.clientes AS novo
    JOIN limpo.clientes AS antigo
        ON antigo.id_cliente < novo.id_cliente
        AND antigo.tipo_pessoa = novo.tipo_pessoa
),
duplicados AS (
    SELECT
        id_cliente,
        min(id_par) AS id_par,
        concat_ws(', ',
            CASE WHEN bool_or(por_documento) THEN 'documento' END,
            CASE WHEN bool_or(por_telefone) THEN 'telefone' END,
            CASE WHEN bool_or(por_nome) THEN 'nome' END
        ) AS motivo
    FROM pares
    WHERE por_documento OR por_telefone OR por_nome
    GROUP BY id_cliente
)
SELECT
    c.id_cliente,
    coalesce(d.id_par, c.id_cliente) AS id_cliente_unificado,
    d.motivo AS motivo_unificacao
FROM limpo.clientes AS c
LEFT JOIN duplicados AS d USING (id_cliente);


-- Cadastro consolidado: uma linha por pessoa, completando dados faltantes com o duplicado.
CREATE OR REPLACE TABLE limpo.clientes_consolidados AS
SELECT
    u.id_cliente_unificado AS id_cliente,
    arg_min(c.nome, c.id_cliente) AS nome,  -- nome do cadastro mais antigo
    any_value(c.documento) AS documento,
    any_value(c.tipo_pessoa) AS tipo_pessoa,
    arg_max(c.telefone, c.id_cliente) AS telefone,  -- telefone mais recente que existir
    any_value(c.email) AS email,
    min(c.data_cadastro) AS data_cadastro,
    count(*) AS qtd_cadastros
FROM limpo.clientes AS c
JOIN limpo.clientes_unificados AS u USING (id_cliente)
GROUP BY u.id_cliente_unificado;
