import json
from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryType, get_store
from datetime import datetime, timezone

def sync():
    dh = DataHubAdapter()
    store = get_store()
    memories = dh.scroll_incident_memories()

    for m in memories:
        incident_id = m['incident_id']
        dataset_urn = m['dataset_urn']
        root_cause = m.get('root_cause', '')
        summary = m.get('resolution_code_diff', '')
        
        table_name = dataset_urn.split('.')[-1]
        if table_name.endswith(',PROD)'):
            table_name = table_name.replace(',PROD)', '')

        record = MemoryRecord(
            id=incident_id,
            type=MemoryType.INCIDENT,
            entity_urn=dataset_urn,
            title=f"Schema Break: {table_name}",
            summary=summary[:100] + '...' if summary else '',
            detail={'root_cause': root_cause},
            tags=[],
            severity='high',
            agent_id='anamnesis'
        )
        store.add(record)
        
        if 'timestamp' in m:
            store._records[incident_id].created_at = float(m['timestamp']/1000.0)

    store._save()
    print(f'Synced {len(memories)} memories to memory_store.json')

if __name__ == "__main__":
    sync()
