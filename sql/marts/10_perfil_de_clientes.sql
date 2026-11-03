-- Gráfico 10 — Perfil de Clientes (pirâmide demográfica)
-- Pergunta: qual a faixa etária e o gênero dos clientes que compram, e quanto cada grupo gasta?
-- Grão: 1 linha por faixa etária e gênero.
-- Métricas: clientes distintos, receita (US$), pedidos distintos, ticket médio = receita / pedidos distintos.
-- Idade: anos completos na data da última venda (referência fixa, não a data de hoje).
-- Gênero: Male = Masculino (lado esquerdo, azul); Female = Feminino (lado direito, roxo).

with ref as (
    select max(data_pedido) as data_ref from refined.vendas
),
base as (
    select
        v.numero_pedido,
        v.chave_cliente,
        c.genero,
        date_sub('year', c.data_nascimento, r.data_ref) as idade,
        v.quantidade * p.preco_unitario_usd             as receita_usd
    from refined.vendas v
    join refined.produtos p using (chave_produto)
    join refined.clientes c using (chave_cliente)
    cross join ref r
)
select
    case
        when idade < 25 then '18–24'
        when idade < 35 then '25–34'
        when idade < 45 then '35–44'
        when idade < 55 then '45–54'
        when idade < 65 then '55–64'
        when idade < 75 then '65–74'
        else '75+'
    end                                                        as faixa_etaria,
    genero,
    count(distinct chave_cliente)                              as clientes,
    sum(receita_usd)                                           as receita_usd,
    count(distinct numero_pedido)                              as pedidos,
    round(sum(receita_usd) / count(distinct numero_pedido), 2) as ticket_medio_usd
from base
group by faixa_etaria, genero
order by faixa_etaria, genero;
