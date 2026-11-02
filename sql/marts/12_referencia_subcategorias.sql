-- Referências do Gráfico 05 — Receita × Margem por Subcategoria (linhas dos quadrantes)
-- Pergunta: onde ficam a receita mediana e a margem global, para separar "alta receita / baixa margem" de "nicho de alta margem"?
-- Grão: 1 linha.
-- Métricas: mediana da receita POR SUBCATEGORIA (US$) e margem global % ponderada (lucro / receita).

with por_subcategoria as (
    select
        p.subcategoria,
        sum(v.quantidade * p.preco_unitario_usd)                          as receita_usd,
        sum(v.quantidade * (p.preco_unitario_usd - p.custo_unitario_usd)) as lucro_usd
    from refined.vendas v
    join refined.produtos p using (chave_produto)
    group by p.subcategoria
)
select
    median(receita_usd)                           as mediana_receita_usd,
    round(100 * sum(lucro_usd) / sum(receita_usd), 1) as margem_global_pct
from por_subcategoria;
