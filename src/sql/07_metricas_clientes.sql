-- 07_metricas_clientes.sql
-- Uma linha por cliente (já unificado), com frequência, gasto e o PERFIL DESCOBERTO pelo
-- comportamento, já que o ERP não registra se a pessoa é motoboy.
--
-- Visita = um dia em que o cliente comprou no balcão ou abriu uma OS concluída.
-- Perfil:
--   Frota        = pessoa jurídica ou 3+ motos (placas) diferentes na oficina;
--   Motoboy      = 6+ visitas com intervalo médio de até 45 dias (troca de óleo mensal);
--   Uso pessoal  = demais clientes com compras.
-- Status (comparando o tempo desde a última visita com o intervalo habitual do cliente):
--   Ativo    = até 2x o intervalo habitual;
--   Em risco = até 4x;  Inativo = mais que isso.
--   O intervalo habitual mínimo é 30 dias (motoboy/frota) ou 60 dias (uso pessoal).

CREATE OR REPLACE VIEW analise.clientes_perfil AS
WITH visitas AS (
    SELECT id_cliente, data FROM analise.itens_vendidos
    WHERE origem = 'Balcão' AND id_cliente IS NOT NULL
    UNION  -- UNION sem ALL remove repetidos: dois pedidos no mesmo dia = uma visita
    SELECT id_cliente, data_abertura FROM analise.ordens_concluidas
    WHERE id_cliente IS NOT NULL
),
frequencia AS (
    SELECT
        id_cliente,
        count(*) AS qtd_visitas,
        min(data) AS primeira_visita,
        max(data) AS ultima_visita,
        CASE WHEN count(*) > 1 THEN (max(data) - min(data)) / (count(*) - 1) END
            AS intervalo_medio_dias
    FROM visitas
    GROUP BY id_cliente
),
gasto AS (
    SELECT id_cliente, data, receita FROM analise.itens_vendidos WHERE id_cliente IS NOT NULL
    UNION ALL
    SELECT id_cliente, data_abertura, valor_mao_obra FROM analise.ordens_concluidas
    WHERE id_cliente IS NOT NULL
),
gasto_total AS (
    SELECT
        g.id_cliente,
        sum(g.receita) AS gasto_total,
        coalesce(sum(g.receita) FILTER (WHERE g.data > r.data_referencia - 365), 0)
            AS gasto_12m
    FROM gasto AS g
    CROSS JOIN analise.referencia AS r
    GROUP BY g.id_cliente
),
motos AS (
    SELECT id_cliente, count(DISTINCT placa) AS qtd_motos, mode(moto) AS moto_principal
    FROM analise.ordens_concluidas
    WHERE id_cliente IS NOT NULL
    GROUP BY id_cliente
),
perfil AS (
    SELECT
        c.id_cliente,
        c.nome,
        c.telefone,
        c.tipo_pessoa,
        c.qtd_cadastros,
        f.qtd_visitas,
        f.primeira_visita,
        f.ultima_visita,
        f.intervalo_medio_dias,
        r.data_referencia - f.ultima_visita AS dias_desde_ultima_visita,
        g.gasto_total,
        g.gasto_12m,
        coalesce(m.qtd_motos, 0) AS qtd_motos,
        m.moto_principal,
        CASE
            WHEN f.qtd_visitas IS NULL THEN 'Sem compras'
            WHEN c.tipo_pessoa = 'PJ' OR m.qtd_motos >= 3 THEN 'Frota'
            WHEN f.qtd_visitas >= 6 AND f.intervalo_medio_dias <= 45 THEN 'Motoboy'
            ELSE 'Uso pessoal'
        END AS perfil
    FROM limpo.clientes_consolidados AS c
    LEFT JOIN frequencia AS f USING (id_cliente)
    LEFT JOIN gasto_total AS g USING (id_cliente)
    LEFT JOIN motos AS m USING (id_cliente)
    CROSS JOIN analise.referencia AS r
)
SELECT
    *,
    CASE
        WHEN qtd_visitas IS NULL THEN 'Sem compras'
        WHEN dias_desde_ultima_visita <= 2 * intervalo_habitual THEN 'Ativo'
        WHEN dias_desde_ultima_visita <= 4 * intervalo_habitual THEN 'Em risco'
        ELSE 'Inativo'
    END AS status
FROM (
    SELECT
        *,
        CASE
            WHEN perfil IN ('Motoboy', 'Frota') THEN greatest(intervalo_medio_dias, 30)
            ELSE greatest(coalesce(intervalo_medio_dias, 60), 60)
        END AS intervalo_habitual
    FROM perfil
);


-- Troca de óleo prevista por cliente: pelo ritmo de cada um, quando ele deve voltar.
-- Troca = OS de troca de óleo ou revisão (que inclui óleo) ou compra de óleo no balcão.
-- Precisa de 3+ trocas para o ritmo ser confiável; o intervalo é a MEDIANA entre trocas
-- (uma viagem ou um mês sem vir não distorce, como distorceria a média).
-- Situação na data de referência:
--   Esta semana    = a próxima troca cai nos próximos 7 dias;
--   Atrasada       = passou da data há até 15 dias (ainda dá tempo de chamar);
--   Muito atrasada = passou há mais de 15 dias;  Em dia = falta mais de uma semana.
CREATE OR REPLACE VIEW analise.clientes_troca_oleo AS
WITH trocas AS (
    SELECT id_cliente, data_abertura AS data
    FROM analise.ordens_concluidas
    WHERE servico IN ('Troca de óleo', 'Revisão geral') AND id_cliente IS NOT NULL
    UNION  -- sem ALL: duas trocas no mesmo dia contam como uma
    SELECT id_cliente, data
    FROM analise.itens_vendidos
    WHERE origem = 'Balcão' AND id_cliente IS NOT NULL AND descricao ILIKE 'Óleo %'
),
intervalos AS (
    SELECT id_cliente, data, data - lag(data) OVER (PARTITION BY id_cliente ORDER BY data) AS dias
    FROM trocas
),
ritmo AS (
    SELECT
        id_cliente,
        count(*) AS qtd_trocas,
        max(data) AS ultima_troca,
        round(median(dias))::INTEGER AS intervalo_dias
    FROM intervalos
    GROUP BY id_cliente
    HAVING count(*) >= 3
),
previsao AS (
    SELECT
        p.id_cliente,
        p.nome,
        p.telefone,
        p.perfil,
        p.moto_principal,
        p.gasto_12m,
        t.qtd_trocas,
        t.ultima_troca,
        t.intervalo_dias,
        t.ultima_troca + t.intervalo_dias AS proxima_troca,
        (t.ultima_troca + t.intervalo_dias) - r.data_referencia AS dias_para_troca
    FROM ritmo AS t
    JOIN analise.clientes_perfil AS p USING (id_cliente)
    CROSS JOIN analise.referencia AS r
)
SELECT
    *,
    CASE
        WHEN dias_para_troca > 7 THEN 'Em dia'
        WHEN dias_para_troca >= 0 THEN 'Esta semana'
        WHEN dias_para_troca >= -15 THEN 'Atrasada'
        ELSE 'Muito atrasada'
    END AS situacao
FROM previsao;
