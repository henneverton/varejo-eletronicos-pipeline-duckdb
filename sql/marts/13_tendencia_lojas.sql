-- Referência do Gráfico 09 — Desempenho das Lojas (linha de tendência)
-- Pergunta: lojas maiores vendem mais, e quanto da variação da receita a área explica?
-- Grão: 1 linha.
-- Métricas: nº de lojas, inclinação e intercepto da reta (receita = intercepto + inclinação × m²) e R².
-- Base: mesmas lojas do mart 09 — físicas (chave_loja <> 0) COM venda; a loja online não tem área.

with lojas_receita as (
    select
        l.chave_loja,
        l.metros_quadrados,
        sum(v.quantidade * p.preco_unitario_usd) as receita_usd
    from refined.vendas v
    join refined.produtos p using (chave_produto)
    join refined.lojas l using (chave_loja)
    where v.chave_loja <> 0
    group by all
)
select
    count(*)                                          as lojas,
    regr_slope(receita_usd, metros_quadrados)         as inclinacao,
    regr_intercept(receita_usd, metros_quadrados)     as intercepto,
    regr_r2(receita_usd, metros_quadrados)            as r2
from lojas_receita;
