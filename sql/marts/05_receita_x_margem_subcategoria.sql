-- Gráfico 05 — Receita × Margem por Subcategoria (bolhas)
-- Pergunta: quais subcategorias vendem muito com pouca margem, e quais são nichos de alta margem?
-- Grão: 1 linha por subcategoria.
-- Métricas: X = receita (US$), Y = margem % ponderada, tamanho da bolha = itens vendidos.

select
    p.subcategoria,
    p.categoria,
    sum(v.quantidade * p.preco_unitario_usd) as receita_usd,
    round(100 * sum(v.quantidade * (p.preco_unitario_usd - p.custo_unitario_usd))
              / sum(v.quantidade * p.preco_unitario_usd), 1) as margem_pct,
    sum(v.quantidade)                        as itens
from refined.vendas v
join refined.produtos p using (chave_produto)
group by p.subcategoria, p.categoria
order by receita_usd desc;
