-- Gráfico 03 — Receita por Categoria (barras horizontais, maior para menor)
-- Pergunta: quais categorias concentram a receita?
-- Grão: 1 linha por categoria.
-- Métricas: receita (US$), participação % no total, itens vendidos.

select
    p.categoria,
    sum(v.quantidade * p.preco_unitario_usd) as receita_usd,
    round(100 * sum(v.quantidade * p.preco_unitario_usd)
              / sum(sum(v.quantidade * p.preco_unitario_usd)) over (), 1) as participacao_pct,
    sum(v.quantidade)                        as itens
from refined.vendas v
join refined.produtos p using (chave_produto)
group by p.categoria
order by receita_usd desc;
