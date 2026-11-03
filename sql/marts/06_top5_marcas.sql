-- Gráfico 06 — Top 5 Marcas (colunas verticais)
-- Pergunta: quais marcas concentram as vendas?
-- Grão: 1 linha por marca (apenas as 5 de maior receita).
-- Métricas: receita (US$), participação % no total geral, itens vendidos.

with marcas as (
    select
        p.marca,
        sum(v.quantidade * p.preco_unitario_usd) as receita_usd,
        sum(v.quantidade)                        as itens
    from refined.vendas v
    join refined.produtos p using (chave_produto)
    group by p.marca
)
select
    marca,
    receita_usd,
    round(100 * receita_usd / sum(receita_usd) over (), 1) as participacao_pct,
    itens
from marcas
order by receita_usd desc
limit 5;
