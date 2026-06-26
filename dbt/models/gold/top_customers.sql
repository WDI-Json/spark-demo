{{ config(materialized='view') }}

select
    customer_id,
    count(*)            as n_orders,
    sum(amount)         as total_revenue
from {{ ref('stg_orders') }}
group by customer_id
order by total_revenue desc
