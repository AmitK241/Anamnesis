from backend.core.datahub_client import DataHubAdapter
import json

client = DataHubAdapter()

urns = [
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.order_items,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.promotions,PROD)",
]

for urn in urns:
    print(f"--- {urn} ---")
    schema_fields = client.get_schema(urn)
    if schema_fields:
        for field in schema_fields:
            print(f"  {field.get('fieldPath')} ({field.get('type')})")
    else:
        print("  NO SCHEMA")
