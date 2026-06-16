{{ config(materialized='table') }}

select
    order_date,
    count(*)            as n_orders,
    sum(amount)         as revenue
from {{ ref('stg_orders') }}
group by order_date
order by order_date
