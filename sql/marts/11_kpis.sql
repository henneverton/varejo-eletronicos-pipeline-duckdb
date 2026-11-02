-- KPIs do dashboard (4 cartões)
-- Pergunta: qual o tamanho do negócio no período inteiro (2016 até 20/02/2021)?
-- Grão: 1 linha (total geral).
-- Métricas: receita (US$), lucro, margem % PONDERADA = lucro / receita (nunca média de margens), itens, clientes distintos, pedidos distintos.
-- Observação: receita = quantidade × preço de tabela do cadastro atual (sem histórico); codigo_moeda e câmbio não entram.

select
    sum(v.quantidade * p.preco_unitario_usd)                           as receita_usd,
    sum(v.quantidade * (p.preco_unitario_usd - p.custo_unitario_usd))  as lucro_usd,
    round(100 * sum(v.quantidade * (p.preco_unitario_usd - p.custo_unitario_usd))
              / sum(v.quantidade * p.preco_unitario_usd), 1)           as margem_pct,
    sum(v.quantidade)                                                  as itens,
    count(distinct v.chave_cliente)                                    as clientes,
    count(distinct v.numero_pedido)                                    as pedidos
from refined.vendas v
join refined.produtos p using (chave_produto);
