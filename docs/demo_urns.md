# Dataset URNs — Confirmed from DataHub (scratch_audit.py)

All URNs verified against live DataHub instance. Platform: postgres.
Audit run: 2026-07-31.

## Primary Demo Datasets

| Dataset | URN | Platform | Lineage | Notes |
|---------|-----|----------|---------|-------|
| orders | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)` | postgres | downstream: order_details view | Primary fact table — Incident 1 |
| customers | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)` | postgres | — | CRM customer master — Incident 2 |
| products | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)` | postgres | — | Product catalog — Incident 3 |

## Supporting Tables (present in DataHub, not used in demo incidents)

| Dataset | URN | Platform |
|---------|-----|----------|
| shipments | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.logistics.shipments,PROD)` | postgres |
| product_categories | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.product_categories,PROD)` | postgres |
| promotions | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.promotions,PROD)` | postgres |
| warehouses | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.warehouses,PROD)` | postgres |
| addresses | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.addresses,PROD)` | postgres |
| regions | `urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.regions,PROD)` | postgres |

## Key Schema Fields Used in Demo

### orders
- `order_status` — NUMBER — **DROPPED** in Incident 1
- `order_id`, `customer_id`, `order_total`, `order_date` — core fields
- `delivery_type`, `payment_method_code`, `order_mode` — auxiliary

### customers (crm_db)
- `customer_class` — STRING — **DROPPED** in Incident 2
- `customer_id`, `cust_first_name`, `cust_last_name`, `cust_email` — PII
- `credit_limit`, `customer_since`, `region_id` — segmentation

### products
- `min_price` — NUMBER — **DROPPED** in Incident 3
- `list_price` — NUMBER — **TYPE CHANGED** NUMBER→STRING in Incident 3
- `product_id`, `product_name`, `product_status`, `category_id` — catalog

## Also Available (dbt + S3 mirrors)

DataHub also contains dbt and S3 platform versions of the same tables:
- `urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.orders,PROD)`
- `urn:li:dataset:(urn:li:dataPlatform:s3,b2fd91.demo-data-bucket/order_entry/orders,PROD)`

For the demo, we exclusively use the **postgres** platform URNs.
