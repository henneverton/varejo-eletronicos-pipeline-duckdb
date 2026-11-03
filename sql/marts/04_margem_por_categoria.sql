-- Gráfico 04 — Margem por Categoria (barras horizontais)
-- Pergunta: quais categorias são mais e menos rentáveis?
-- Grão: 1 linha por categoria.
-- Métricas: receita, lucro (receita − custo) e margem % PONDERADA = lucro / receita (nunca média de margens).
-- Observação: custo e preço são os do cadastro atual de produtos (sem histórico).

select
    p.categoria,
    sum(v.quantidade * p.preco_unitario_usd)                           as receita_usd,
    sum(v.quantidade * (p.preco_unitario_usd - p.custo_unitario_usd))  as lucro_usd,
    round(100 * sum(v.quantidade * (p.preco_unitario_usd - p.custo_unitario_usd))
              / sum(v.quantidade * p.preco_unitario_usd), 1)           as margem_pct
from refined.vendas v
join refined.produtos p using (chave_produto)
group by p.categoria
order by margem_pct desc;
