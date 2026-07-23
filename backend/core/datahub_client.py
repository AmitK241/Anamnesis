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
        with urllib.request.urlopen(req, timeout=15) as resp:
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
        Get lineage graph for an entity.
        direction: UPSTREAM | DOWNSTREAM
        Returns raw GraphQL response dict.
        """
        gql = """
        query Lineage($urn: String!, $input: LineageInput!) {
          entity(urn: $urn) {
            urn
            type
            ... on Dataset { name }
            lineage(input: $input) {
              relationships {
                entity { urn type ... on Dataset { name } }
              }
            }
          }
        }
        """
        try:
            return self._gql(gql, {
                "urn": urn,
                "input": {"direction": direction, "count": 100},
            })
        except Exception as exc:
            logger.error("get_lineage failed for %s: %s", urn, exc)
            return {}

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
