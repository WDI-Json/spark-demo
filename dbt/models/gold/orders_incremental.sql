{{ config(
		materialized='incremental',
		unique_key='order_id'
) }}

select * from {{ ref('stg_orders') }}

{% if is_incremental() %}
	where order_date > (select max(order_date) from {{ this }})
{% endif %}
