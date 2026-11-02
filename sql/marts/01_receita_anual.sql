-- Gráfico 01 — Receita Anual (colunas)
-- Pergunta: como a receita evoluiu ao longo dos anos e qual foi o melhor ano?
-- Grão: 1 linha por ano.
-- Métricas: receita (quantidade × preço de tabela, US$), pedidos distintos, variação % contra o ano anterior.
-- Observação: variação = NULL para ano parcial (menos de 12 meses com venda), ex.: 2021 vai só até 20/02.

with base as (
    select
        year(v.data_pedido)                 as ano,
        month(v.data_pedido)                as mes,
        v.numero_pedido,
        v.quantidade * p.preco_unitario_usd as receita_usd
    from refined.vendas v
    join refined.produtos p using (chave_produto)
),
anual as (
    select
        ano,
        count(distinct mes)           as meses_com_venda,
        count(distinct numero_pedido) as pedidos,
        sum(receita_usd)              as receita_usd
    from base
    group by ano
)
select
    ano,
    meses_com_venda,
    pedidos,
    receita_usd,
    case when meses_com_venda = 12
         then round(100 * (receita_usd / lag(receita_usd) over (order by ano) - 1), 1)
    end                                    as variacao_pct,
    receita_usd = max(receita_usd) over () as melhor_ano
from anual
order by ano;
