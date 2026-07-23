# Dataset URNs with Good Lineage Chains

To be filled in after Step 4 (datahub datapack load showcase-ecommerce)

## Format
Each URN below should have upstream → downstream lineage for the demo schema-break scenario.

| Dataset | URN | Platform | Notes |
|---------|-----|----------|-------|
| orders  | TBD | TBD      | Primary fact table – used in schema-break demo |
| customers | TBD | TBD    | Upstream of orders |
| revenue_dashboard | TBD | TBD | Downstream consumer of orders |

## Instructions
1. After `datahub datapack load showcase-ecommerce` completes, open http://localhost:9002
2. Search for "orders" → click the dataset → note the URN in the browser URL bar
3. Click the "Lineage" tab to confirm upstream/downstream chains exist
4. Paste the URNs into this table

## Example URN format (DataHub)
```
urn:li:dataset:(urn:li:dataPlatform:snowflake,ecommerce.public.orders,PROD)
urn:li:dataset:(urn:li:dataPlatform:snowflake,ecommerce.public.customers,PROD)
```
