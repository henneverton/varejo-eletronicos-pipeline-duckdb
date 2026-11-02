-- Gráfico 07 — Receita por País (mapa coroplético + ranking)
-- Pergunta: em quais países está concentrada a receita?
-- Grão: 1 linha por país do CLIENTE.
-- Métricas: receita (US$), participação % no total, clientes distintos, pedidos distintos.
-- Observação: usa o país do cliente porque a loja online não tem país; nas vendas físicas coincide com o da loja.

select
    c.pais,
    c.continente,
    sum(v.quantidade * p.preco_unitario_usd) as receita_usd,
    round(100 * sum(v.quantidade * p.preco_unitario_usd)
              / sum(sum(v.quantidade * p.preco_unitario_usd)) over (), 1) as participacao_pct,
    count(distinct v.chave_cliente)          as clientes,
    count(distinct v.numero_pedido)          as pedidos
from refined.vendas v
join refined.produtos p using (chave_produto)
join refined.clientes c using (chave_cliente)
group by c.pais, c.continente
order by receita_usd desc;
