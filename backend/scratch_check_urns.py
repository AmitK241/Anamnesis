from backend.core.datahub_client import DataHubAdapter

urns = [
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.products,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.products,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.crm_db.customers,PROD)"
]

dh = DataHubAdapter()
for urn in urns:
    exists = dh.graph.exists(urn)
    print(f"{urn} EXISTS: {exists}")
