"""
Anamnesis – DataHub Client Wrapper
====================================

Thin adapter over the DataHub Python SDK that the Anamnesis agents use to:
  - Search datasets, dashboards, and data jobs
  - Retrieve schema fields and column lineage
  - Read and write custom structured properties (incident memory records)
  - Traverse upstream / downstream lineage graphs

Reads connection config from environment variables:
  DATAHUB_GMS_SERVER  – e.g. http://localhost:8080
  DATAHUB_GMS_TOKEN   – Personal Access Token (optional for local dev)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataHubAdapter:
    """
    Wrapper around the DataHub REST + GraphQL APIs.
    Falls back to direct HTTP if the SDK is not fully available.
    """

    def __init__(
        self,
        server: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.server = (server or os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")).rstrip("/")
        self.token = token or os.getenv("DATAHUB_GMS_TOKEN", "")
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from datahub.sdk.main_client import DataHubClient  # type: ignore

            self._client = DataHubClient(
                server=self.server,
                token=self.token or None,
            )
            logger.info("DataHubClient SDK connected to %s", self.server)
        except ImportError:
            logger.warning("DataHub SDK not available; falling back to raw HTTP calls")

    # ── health ────────────────────────────────────────────────────────────────

    def health(self) -> bool:
        """Ping the GMS /health endpoint. Returns True if healthy."""
        import urllib.request

        try:
            res = urllib.request.urlopen(f"{self.server}/health", timeout=5)
            return res.status == 200
        except Exception as exc:
            logger.error("DataHub GMS health check failed: %s", exc)
            return False

    # ── GraphQL helpers ───────────────────────────────────────────────────────

    def _gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import json
        import urllib.request

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(
            f"{self.server}/api/graphql",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read())

    # ── search ────────────────────────────────────────────────────────────────

    def search_datasets(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for datasets by keyword. Returns list of {urn, name, platform, description}."""
        gql = """
        query Search($input: SearchInput!) {
          search(input: $input) {
            count
            searchResults {
              entity {
                urn
                type
                ... on Dataset {
                  name
                  platform { name }
                  editableProperties { description }
                  properties { description }
                }
              }
            }
          }
        }
        """
        try:
            data = self._gql(gql, {"input": {"type": "DATASET", "query": query, "start": 0, "count": limit}})
            results = []
            for r in data.get("data", {}).get("search", {}).get("searchResults", []):
                e = r["entity"]
                results.append({
                    "urn": e["urn"],
                    "name": e.get("name", ""),
                    "platform": e.get("platform", {}).get("name", ""),
                    "description": (
                        (e.get("editableProperties") or {}).get("description")
                        or (e.get("properties") or {}).get("description")
                        or ""
                    ),
                })
            return results
        except Exception as exc:
            logger.error("search_datasets failed: %s", exc)
            return []

    # ── lineage ───────────────────────────────────────────────────────────────

    def get_lineage(
        self,
        urn: str,
        direction: str = "DOWNSTREAM",
        depth: int = 3,
    ) -> Dict[str, Any]:
        """
        Get direct (1-hop) lineage for a dataset via ``dataset.lineage``.
        direction: UPSTREAM | DOWNSTREAM
        Returns the raw GraphQL response dict.
        """
        gql = """
        query Lineage($urn: String!, $direction: String!, $count: Int!) {
          dataset(urn: $urn) {
            name
            lineage(input: {direction: $direction, count: $count}) {
              relationships {
                entity {
                  urn
                  type
                  ... on Dataset { name }
                  ... on DataJob  { jobId dataFlow { flowId } }
                  ... on Dashboard { dashboardId }
                }
              }
            }
          }
        }
        """
        try:
            return self._gql(gql, {"urn": urn, "direction": direction, "count": 100})
        except Exception as exc:
            logger.error("get_lineage failed for %s: %s", urn, exc)
            return {}

    def get_lineage_scroll(
        self,
        urn: str,
        direction: str = "DOWNSTREAM",
        max_hops: int = 3,
        count: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Multi-hop lineage via ``scrollAcrossLineage``.
        Returns list of {urn, type, name, degree} dicts, de-duplicated.
        direction: UPSTREAM | DOWNSTREAM
        """
        gql = """
        query ScrollLineage($urn: String!, $direction: LineageDirection!, $count: Int!) {
          scrollAcrossLineage(input: {
            urn: $urn
            direction: $direction
            count: $count
            query: "*"
          }) {
            searchResults {
              degree
              entity {
                urn
                type
                ... on Dataset  { name }
                ... on DataJob  { jobId }
                ... on Dashboard { dashboardId }
              }
            }
          }
        }
        """
        try:
            data = self._gql(gql, {
                "urn": urn,
                "direction": direction.upper(),
                "count": count,
            })
            results = (
                data.get("data", {})
                    .get("scrollAcrossLineage", {})
                    .get("searchResults", [])
            )
            seen: set = set()
            entities: List[Dict[str, Any]] = []
            for r in results:
                e = r.get("entity") or {}
                entity_urn = e.get("urn", "")
                if not entity_urn or entity_urn in seen:
                    continue
                seen.add(entity_urn)
                entities.append({
                    "urn":    entity_urn,
                    "type":   e.get("type", ""),
                    "name":   e.get("name") or e.get("jobId") or e.get("dashboardId") or "",
                    "degree": r.get("degree", 1),
                })
            return entities
        except Exception as exc:
            logger.error("get_lineage_scroll failed for %s: %s", urn, exc)
            return []

    # ── schema ────────────────────────────────────────────────────────────────

    def get_schema(self, dataset_urn: str) -> List[Dict[str, Any]]:
        """Return list of schema fields: [{fieldPath, type, description}]."""
        gql = """
        query Schema($urn: String!) {
          dataset(urn: $urn) {
            schemaMetadata {
              fields {
                fieldPath
                type
                description
              }
            }
          }
        }
        """
        try:
            data = self._gql(gql, {"urn": dataset_urn})
            fields = (
                data.get("data", {})
                .get("dataset", {})
                .get("schemaMetadata", {})
                .get("fields", [])
            )
            return [
                {
                    "fieldPath": f["fieldPath"],
                    "type": f.get("type", ""),
                    "description": f.get("description", ""),
                }
                for f in fields
            ]
        except Exception as exc:
            logger.error("get_schema failed for %s: %s", dataset_urn, exc)
            return []

    # ── assertions / incidents ────────────────────────────────────────────────

    def get_recent_incidents(self, dataset_urn: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return recent DataHub incidents for a dataset (if any)."""
        # Note: Incidents API varies by DataHub version; returns empty list if unavailable.
        gql = """
        query Incidents($urn: String!, $count: Int!) {
          dataset(urn: $urn) {
            incidents(state: ACTIVE, count: $count) {
              incidents {
                urn
                title
                description
                status { state }
                created { time }
              }
            }
          }
        }
        """
        try:
            data = self._gql(gql, {"urn": dataset_urn, "count": limit})
            incidents = (
                data.get("data", {})
                .get("dataset", {})
                .get("incidents", {})
                .get("incidents", [])
            )
            return incidents
        except Exception as exc:
            logger.debug("get_recent_incidents not supported or failed: %s", exc)
            return []

    # ── incidentMemory aspect scroll ──────────────────────────────────────────

    def scroll_incident_memories(self, max_results: int = 500) -> List[Dict[str, Any]]:
        """
        Fetch ALL IncidentMemory aspects stored across datasets in DataHub.

        Strategy (tried in order):
        1. GraphQL ``searchAcrossEntities`` with an ``_exists_`` filter for the
           ``incidentMemory`` aspect — works on DataHub >= 0.12 with OpenSearch.
        2. Env-var fallback: read ``ANAMNESIS_KNOWN_DATASET_URNS`` (pipe-separated
           list of dataset URNs, e.g. ``urn:li:....|urn:li:....``).  Use ``|``
           not ``,`` because DataHub URNs themselves contain commas.
           This is always populated by verify scripts.

        Returns a list of dicts, one per stored IncidentMemory, each containing::

            {
                "dataset_urn":           str,
                "incident_id":           str,
                "root_cause":            str,
                "embedding_vector":      list[float],
                "resolution_code_diff":  str,
                "time_saved_estimate":   int,
                "downstream_impact":     list[str],
                "timestamp":             int,
            }

        Missing optional fields default to empty/zero.  Records with no
        ``embeddingVector`` or an empty one are included (recall agent will
        skip them since cosine_similarity returns 0.0 for zero vectors).
        """
        import json
        import urllib.parse
        import urllib.request

        urns: List[str] = []

        # ── Strategy 1: GraphQL _exists_ filter ───────────────────────────────
        try:
            gql = """
            query FindIncidentMemoryDatasets($count: Int!) {
              searchAcrossEntities(input: {
                types: [DATASET]
                query: "*"
                count: $count
                filters: [{field: "_exists_", values: ["incidentMemory"]}]
              }) {
                searchResults { entity { urn } }
              }
            }
            """
            data = self._gql(gql, {"count": max_results})
            results = (
                data.get("data", {})
                    .get("searchAcrossEntities", {})
                    .get("searchResults", [])
            )
            gql_urns = [r["entity"]["urn"] for r in results if r.get("entity", {}).get("urn")]
            if gql_urns:
                logger.info(
                    "scroll_incident_memories: found %d dataset(s) via GraphQL _exists_ filter",
                    len(gql_urns),
                )
                urns = gql_urns
            else:
                logger.debug("GraphQL _exists_ filter returned 0 results — trying fallback")
        except Exception as exc:
            logger.debug("GraphQL _exists_ filter not supported or failed: %s", exc)

        # ── Strategy 2: env-var fallback ─────────────────────────────────────
        if not urns:
            env_urns = os.getenv("ANAMNESIS_KNOWN_DATASET_URNS", "")
            if env_urns.strip():
                # Split on | because DataHub URNs contain commas internally
                urns = [u.strip() for u in env_urns.split("|") if u.strip()]
                logger.info(
                    "scroll_incident_memories: using %d URN(s) from "
                    "ANAMNESIS_KNOWN_DATASET_URNS env var",
                    len(urns),
                )

        # ── Strategy 3: broad dataset scan ───────────────────────────────
        # Custom aspects are NOT reliably indexed by DataHub's _exists_ filter.
        # If we only rely on Strategy 1, we may miss canonical incidents that
        # weren't indexed, while picking up __WIPED__ ones that were.
        # We always fetch all dataset URNs and merge them.
        try:
            gql_all = """
            query AllDatasets($count: Int!) {
              searchAcrossEntities(input: {
                types: [DATASET]
                query: "*"
                count: $count
              }) {
                searchResults { entity { urn } }
              }
            }
            """
            data_all = self._gql(gql_all, {"count": max_results})
            all_results = (
                data_all.get("data", {})
                       .get("searchAcrossEntities", {})
                       .get("searchResults", [])
            )
            all_urns = [
                r["entity"]["urn"]
                for r in all_results
                if r.get("entity", {}).get("urn")
            ]
            if all_urns:
                logger.info(
                    "scroll_incident_memories: broad scan — probing %d dataset(s) for "
                    "incidentMemory aspect",
                    len(all_urns),
                )
                # Merge and deduplicate with any URNs found in Strategy 1/2
                urns = list(set(urns + all_urns))
            else:
                logger.info(
                    "scroll_incident_memories: broad scan returned 0 datasets; "
                    "continuing with %d URN(s)", len(urns)
                )
        except Exception as exc:
            logger.warning("scroll_incident_memories: broad scan failed: %s", exc)
        if not urns:
            return []

        # ── Fetch aspect for each URN ─────────────────────────────────────────
        records: List[Dict[str, Any]] = []
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        import concurrent.futures

        def fetch_aspect(urn: str) -> Optional[Dict[str, Any]]:
            encoded = urllib.parse.quote(urn, safe="")
            url = f"{self.server}/aspects/{encoded}?aspect=incidentMemory&version=0"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    raw = json.loads(resp.read())

                aspect_data = raw.get("aspect", {})
                if isinstance(aspect_data, dict) and "value" in aspect_data:
                    try:
                        aspect_data = json.loads(aspect_data["value"])
                    except json.JSONDecodeError:
                        pass
                if isinstance(aspect_data, dict) and len(aspect_data) == 1:
                    only_key = next(iter(aspect_data))
                    if "." in only_key:
                        aspect_data = aspect_data[only_key]

                if not isinstance(aspect_data, dict):
                    return None

                incident_id = aspect_data.get("incidentId", "")
                if not incident_id or incident_id == "__WIPED__":
                    return None

                return {
                    "dataset_urn":          urn,
                    "incident_id":          incident_id,
                    "root_cause":           aspect_data.get("rootCause", ""),
                    "embedding_vector":     aspect_data.get("embeddingVector", []),
                    "resolution_code_diff": aspect_data.get("resolutionCodeDiff", ""),
                    "time_saved_estimate":  aspect_data.get("timeSavedEstimate", 0),
                    "downstream_impact":    aspect_data.get("downstreamImpact", []),
                    "timestamp":            aspect_data.get("timestamp", 0),
                }
            except Exception as exc:
                if "404" not in str(exc):
                    logger.debug("Could not fetch incidentMemory for %s: %s", urn, exc)
                return None

        # Fetch in parallel (max 10 workers to not overwhelm GMS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for result in executor.map(fetch_aspect, urns):
                if result:
                    records.append(result)

        # ── Strategy 4: Local memory_store.json fallback ──────────────────────
        # Since DataHub GMS is unstable, augment/fallback with local store
        try:
            from backend.core.memory_store import get_store
            store = get_store()
            local_ids = {r["incident_id"] for r in records}
            for rec in store.all():
                if rec.type.name == "INCIDENT" and rec.id not in local_ids:
                    detail = rec.detail or {}
                    vec = detail.get("embedding_vector", [])
                    if vec:
                        records.append({
                            "dataset_urn":          rec.entity_urn,
                            "incident_id":          rec.id,
                            "root_cause":           rec.summary,
                            "embedding_vector":     vec,
                            "resolution_code_diff": detail.get("suggested_fix", ""),
                            "time_saved_estimate":  detail.get("time_saved_estimate", 0),
                            "downstream_impact":    detail.get("downstream_impact", []),
                            "timestamp":            detail.get("timestamp", 0),
                        })
                        local_ids.add(rec.id)
        except Exception as exc:
            logger.warning("Local memory_store fallback failed: %s", exc)

        logger.info("scroll_incident_memories: loaded %d record(s)", len(records))
        return records
