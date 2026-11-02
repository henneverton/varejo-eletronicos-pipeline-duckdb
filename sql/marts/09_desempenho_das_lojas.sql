-- Gráfico 09 — Desempenho das Lojas (dispersão área × receita + Top/Bottom 10)
-- Pergunta: lojas maiores vendem mais, e quais são as mais e menos produtivas por m²?
-- Grão: 1 linha por loja física COM venda (a loja online fica de fora: não tem área).
-- Métricas: X = metros_quadrados, Y = receita (US$), receita por m², posição no ranking.
-- Uso: ranking_top <= 10 → Top 10; ranking_bottom <= 10 → Bottom 10.
-- Observação: lojas abertas depois de 2016 têm menos tempo de venda e são penalizadas na receita por m².

with lojas_receita as (
    select
        l.chave_loja,
        l.pais,
        l.estado,
        l.metros_quadrados,
        l.data_abertura,
        sum(v.quantidade * p.preco_unitario_usd) as receita_usd
    from refined.vendas v
    join refined.produtos p using (chave_produto)
    join refined.lojas l using (chave_loja)
    where v.chave_loja <> 0
    group by all
)
select
    chave_loja,
    pais,
    estado,
    metros_quadrados,
    data_abertura,
    receita_usd,
    round(receita_usd / metros_quadrados, 2)                   as receita_por_m2,
    rank() over (order by receita_usd / metros_quadrados desc) as ranking_top,
    rank() over (order by receita_usd / metros_quadrados asc)  as ranking_bottom
from lojas_receita
order by ranking_top;
