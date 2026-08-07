import os
import json
from backend.agents.detector import SchemaDetector
from backend.agents.diagnoser import Diagnoser
from backend.agents.recall import MemoryRecallAgent
from backend.agents.fixer import FixerAgent
from backend.agents.memory_writer import MemoryWriterAgent
from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import get_store, MemoryType, MemoryRecord

def main():
    dh = DataHubAdapter()
    store = get_store()
    
    detector = SchemaDetector(datahub=dh, store=store)
    diagnoser = Diagnoser(datahub=dh, store=store)
    recall = MemoryRecallAgent(datahub=dh)
    fixer = FixerAgent()
    writer = MemoryWriterAgent()
    
    # 1. Add MEDIUM severity incident (order_items)
    # ------------------------------------------------
    urn_medium = "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.order_items,PROD)"
    print(f"Processing MEDIUM severity for {urn_medium}...")
    
    live_fields_m = dh.get_schema(urn_medium)
    current_schema_m = { f["fieldPath"]: f.get("type", "STRING") for f in live_fields_m }
    
    if not current_schema_m:
        print("Failed to get live schema for medium URN")
        return

    # known_good_schema for MEDIUM: 
    # Let's change one field's type such that WAS="NUMBER" and NOW="STRING" (non-breaking)
    known_good_m = dict(current_schema_m)
    # Find a STRING field in current_schema_m and pretend it was NUMBER
    for path, typ in current_schema_m.items():
        if typ.upper() == "STRING":
            known_good_m[path] = "NUMBER"
            break
    
    detection_m = detector.detect_schema_break(urn_medium, known_good_m)
    print(f"Medium detection severity: {detection_m.get('severity')}")
    
    diagnosis_m = diagnoser.diagnose(detection_m)
    recall_res_m = recall.recall_similar_incidents(diagnosis_m)
    fix_m = fixer.generate_fix(diagnosis_m, recall_res_m)
    write_m = writer.write_incident_memory(detection_m, diagnosis_m, recall_res_m, fix_m)
    print(f"Medium incident written: {write_m}")


    # 2. Add LOW severity incident (promotions)
    # ------------------------------------------------
    urn_low = "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.promotions,PROD)"
    print(f"\nProcessing LOW severity for {urn_low}...")
    
    live_fields_l = dh.get_schema(urn_low)
    current_schema_l = { f["fieldPath"]: f.get("type", "STRING") for f in live_fields_l }
    
    if not current_schema_l:
        print("Failed to get live schema for low URN")
        return
        
    # known_good_schema for LOW:
    # Let's pretend a field was just added (so it is missing from known_good)
    known_good_l = dict(current_schema_l)
    if known_good_l:
        # pop an arbitrary field
        removed_key = list(known_good_l.keys())[0]
        known_good_l.pop(removed_key)
        
    detection_l = detector.detect_schema_break(urn_low, known_good_l)
    print(f"Low detection severity: {detection_l.get('severity')}")
    
    diagnosis_l = diagnoser.diagnose(detection_l)
    recall_res_l = recall.recall_similar_incidents(diagnosis_l)
    fix_l = fixer.generate_fix(diagnosis_l, recall_res_l)
    write_l = writer.write_incident_memory(detection_l, diagnosis_l, recall_res_l, fix_l)
    print(f"Low incident written: {write_l}")


    # 3. Create 2 SCHEMA_FIX type memory records tied to existing incidents
    # ------------------------------------------------
    print("\nAdding SCHEMA_FIX records...")
    # Get incidents to use
    incidents = store.query(memory_type=MemoryType.INCIDENT, limit=10)
    # pick first two incidents
    if len(incidents) >= 2:
        for inc in incidents[:2]:
            # check if they have fix details
            fix_text = inc.detail.get('suggested_fix')
            if not fix_text:
                fix_text = "Applied schema fix via dbt: updated upstream view to cast types appropriately."
                
            schema_fix_record = MemoryRecord(
                type=MemoryType.SCHEMA_FIX,
                entity_urn=inc.entity_urn,
                title=f"Applied fix for {inc.entity_urn.split('.')[-1]}",
                summary="Implemented suggested fix from Incident.",
                detail={
                    "incident_id": inc.id,
                    "applied_fix": fix_text
                },
                tags=["schema_fix", "resolved"],
                severity="LOW"
            )
            store.add(schema_fix_record)
            print(f"Added SCHEMA_FIX for {inc.entity_urn}")
    else:
        print("Not enough incidents to add SCHEMA_FIX")


    # 4. Mark 2 existing incidents as resolved
    # ------------------------------------------------
    print("\nMarking incidents as resolved...")
    if len(incidents) >= 3:
        for inc in incidents[2:4]:
            store.update(inc.id, resolved=True)
            print(f"Resolved incident {inc.id}")


    # Finally, sync datahub (write the store back to datahub if needed)
    print("\nSyncing local store to DataHub if applicable...")
    from backend.sync_store import main as sync_main
    try:
        # sync_store main function just runs the sync. Let's do it manually just in case
        for rec in store.query():
            dh.write_memory(rec)
        print("Synced to datahub successfully.")
    except Exception as e:
        print(f"Error syncing to datahub: {e}")

if __name__ == '__main__':
    main()
