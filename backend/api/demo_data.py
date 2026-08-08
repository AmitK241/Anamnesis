import time

DEMO_MEMORIES = [
    {
        'id': 'INC-1786124483047-KNJDYZ', 
        'type': 'INCIDENT', 
        'entity_urn': 'urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)', 
        'title': 'Schema break on orders', 
        'summary': "Field(s) 'order_status' no longer exist in the live schema. No upstream lineage edges were found; the break may have been applied directly to this table's DDL. No downstream consumers were found in the lineage graph; impact may be limited to direct API/query consumers.", 
        'detail': {
            'missing_fields': ['order_status'], 
            'type_changes': [], 
            'downstream_impact': [], 
            'suggested_fix': "**One-sentence summary of the break:**\nThe `order_status` field has been removed from the `orders` table in the `order_entry_db` dataset on the Postgres data platform.\n\n**Concrete fix:**\n```sql\nALTER TABLE order_entry_db.order_entry.orders\nADD COLUMN IF NOT EXISTS order_status VARCHAR(50) DEFAULT NULL;\n```\nThis SQL snippet adds the missing `order_status` column with a default value of `NULL` to the `orders` table, ensuring data consistency and allowing for potential downstream processing.", 
            'embedding_vector': [1.0, 0.5, 0.5]
        }, 
        'tags': ['orders', 'schema-break'], 
        'severity': 'CRITICAL', 
        'resolved': False, 
        'created_at': time.time() - 3600, 
        'updated_at': time.time() - 3600, 
        'agent_id': 'anamnesis'
    }, 
    {
        'id': 'INC-1786124500621-2YRHN4', 
        'type': 'INCIDENT', 
        'entity_urn': 'urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)', 
        'title': 'Schema break on customers', 
        'summary': "Field(s) 'customer_class' no longer exist in the live schema. No upstream lineage edges were found; the break may have been applied directly to this table's DDL.", 
        'detail': {
            'missing_fields': ['customer_class'], 
            'type_changes': [], 
            'downstream_impact': [], 
            'suggested_fix': "**One-sentence summary of the break:**\nThe `customer_class` field has been removed from the `customers` table in the `crm_db` dataset on the Postgres data platform.\n\n**Adapted fix:**\n```sql\nALTER TABLE crm_db.customers\nADD COLUMN IF NOT EXISTS customer_class VARCHAR(50) DEFAULT NULL;\n```", 
            'embedding_vector': [0.5, 1.0, 0.5]
        }, 
        'tags': ['customers', 'schema-break'], 
        'severity': 'HIGH', 
        'resolved': True, 
        'created_at': time.time() - 7200, 
        'updated_at': time.time() - 7000, 
        'agent_id': 'anamnesis'
    },
    {
        'id': 'INC-1786124541465-VF8TC6', 
        'type': 'INCIDENT', 
        'entity_urn': 'urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)', 
        'title': 'Schema break on products', 
        'summary': "1 field(s) were removed and 1 field type(s) changed. No upstream lineage edges were found; the break may have been applied directly to this table's DDL.", 
        'detail': {
            'missing_fields': ['min_price'], 
            'type_changes': [{'field': 'list_price', 'was': 'NUMBER', 'now': 'STRING'}], 
            'downstream_impact': [], 
            'suggested_fix': "**One-sentence summary of the break:**\nThe `min_price` field has been removed and `list_price` field type has been changed from NUMBER to STRING in the `products` table.\n\n**Adapted fix:**\n```sql\nALTER TABLE order_entry_db.order_entry.products\nADD COLUMN IF NOT EXISTS min_price NUMBER DEFAULT NULL;\n\nALTER TABLE order_entry_db.order_entry.products\nALTER COLUMN list_price TYPE VARCHAR(50);\n```", 
            'embedding_vector': [0.5, 0.5, 1.0]
        }, 
        'tags': ['products', 'schema-break'], 
        'severity': 'MEDIUM', 
        'resolved': False, 
        'created_at': time.time() - 14400, 
        'updated_at': time.time() - 14400, 
        'agent_id': 'anamnesis'
    }
]
