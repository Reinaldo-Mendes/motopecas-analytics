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
