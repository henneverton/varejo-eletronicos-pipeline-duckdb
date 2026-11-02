-- Gráfico 02 — Receita Mensal com Sazonalidade (linhas, uma por ano)
-- Pergunta: em quais meses o negócio fatura mais e menos, e o padrão se repete entre os anos?
-- Grão: 1 linha por ano e mês.
-- Métricas: receita (US$) e pedidos distintos.
-- Observação: 2021 só tem janeiro e fevereiro (até 20/02).

select
    year(v.data_pedido)                      as ano,
    month(v.data_pedido)                     as mes,
    sum(v.quantidade * p.preco_unitario_usd) as receita_usd,
    count(distinct v.numero_pedido)          as pedidos
from refined.vendas v
join refined.produtos p using (chave_produto)
group by ano, mes
order by ano, mes;
