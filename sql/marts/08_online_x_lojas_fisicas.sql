-- Gráfico 08 — Online × Lojas Físicas (rosca + evolução por ano)
-- Pergunta: qual a participação do online e das lojas físicas, e ela cresce ao longo do tempo?
-- Grão: 1 linha por canal no total geral (ano = 'Total') e 1 linha por ano e canal.
-- Métricas: receita (US$) e participação % dentro do mesmo ano (ou do total).
-- Regra de canal: chave_loja = 0 é a loja "Online"; as demais são lojas físicas.
-- Observação: 2021 é parcial (até 20/02).

with base as (
    select
        year(v.data_pedido)                                             as ano,
        case when v.chave_loja = 0 then 'Online' else 'Loja física' end as canal,
        v.quantidade * p.preco_unitario_usd                             as receita_usd
    from refined.vendas v
    join refined.produtos p using (chave_produto)
),
agrupado as (
    select
        coalesce(cast(ano as varchar), 'Total') as ano,
        canal,
        sum(receita_usd)                        as receita_usd
    from base
    group by grouping sets ((canal), (ano, canal))
)
select
    ano,
    canal,
    receita_usd,
    round(100 * receita_usd / sum(receita_usd) over (partition by ano), 1) as participacao_pct
from agrupado
order by ano <> 'Total', ano, canal;
