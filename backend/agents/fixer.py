"""
Anamnesis – Fixer Agent
========================

Generates a concrete fix suggestion for a detected schema break.

Two modes
---------
adapted
    A past incident with ``similarity_score >= 0.85`` was found by the
    Memory-Recall agent.  The LLM receives the *past* incident's
    ``resolution_code_diff`` + its root-cause, and the *current* diagnosis
    specifics, and is asked to **adapt** the old fix to the new context.
    This is the "fast path" — re-using institutional memory instead of
    solving from scratch.

generated_fresh
    No sufficiently similar past incident exists.  The LLM receives only
    the current diagnosis (root_cause, missing_fields, type_changes,
    downstream_impact) and proposes a brand-new fix.

Usage
-----
    from backend.agents.fixer import FixerAgent

    agent = FixerAgent()
    result = agent.generate_fix(diagnosis, recall_result)

Module-level convenience wrapper (uses a module singleton)::

    from backend.agents.fixer import generate_fix
    result = generate_fix(diagnosis, recall_result)

Return schema
-------------
{
    "mode":                        "adapted" | "generated_fresh",
    "suggested_fix":               str,   # fix text / diff / pseudocode
    "based_on_incident_id":        str | None,
    "confidence_note":             str,
    "estimated_time_saved_minutes": int | None,  # only when adapted
}

Environment
-----------
GROQ_API_KEY     – required.  Set in .env at the project root.
GROQ_MODEL       – optional, defaults to "llama-3.1-8b-instant".
GROQ_TEMPERATURE – optional float, defaults to 0.3.

Error handling
--------------
* Missing GROQ_API_KEY -> raises RuntimeError with clear install hint.
* Groq API error       -> re-raised with context, so the caller can handle.
* Empty recall_result  -> falls through to generated_fresh automatically.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env (project root, one level above backend/)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load .env from the project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv  # type: ignore
        # Walk up from this file: agents/ -> backend/ -> project root
        root = Path(__file__).resolve().parent.parent.parent
        env_path = root / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            logger.debug("FixerAgent: loaded .env from %s", env_path)
        else:
            logger.warning(
                "FixerAgent: no .env file found at %s -- "
                "GROQ_API_KEY must be set in the environment.",
                env_path,
            )
    except ImportError:
        logger.debug("FixerAgent: python-dotenv not installed; skipping .env load")


_load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADAPT_THRESHOLD: float = 0.85   # min similarity_score to trigger "adapted" mode
DEFAULT_MODEL: str = "llama-3.1-8b-instant"
DEFAULT_TEMPERATURE: float = 0.3


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _format_missing_fields(missing_fields: List[str]) -> str:
    if not missing_fields:
        return "(none)"
    return ", ".join(f"`{f}`" for f in missing_fields)


def _format_type_changes(type_changes: List[Dict[str, str]]) -> str:
    if not type_changes:
        return "(none)"
    return "; ".join(
        f"`{tc.get('field', '?')}` changed from {tc.get('was', '?')} -> {tc.get('now', '?')}"
        for tc in type_changes
    )


def _format_downstream(downstream_impact: Any) -> str:
    if not downstream_impact:
        return "(none listed)"
    if isinstance(downstream_impact, list):
        return ", ".join(str(d) for d in downstream_impact[:6])
    return str(downstream_impact)


def _build_adapt_prompt(
    current_diagnosis: Dict[str, Any],
    past_incident: Dict[str, Any],
) -> str:
    """
    Prompt for the 'adapted' mode: give the LLM both the historical fix
    and the current diagnosis so it can tailor the old fix to the new context.
    """
    past_root = past_incident.get("root_cause", "(unknown)")
    past_diff = past_incident.get("resolution_code_diff", "(not recorded)")
    past_id   = past_incident.get("incident_id", "?")

    curr_root    = current_diagnosis.get("root_cause", "(unknown)")
    curr_missing = _format_missing_fields(current_diagnosis.get("missing_fields", []))
    curr_types   = _format_type_changes(current_diagnosis.get("type_changes", []))
    curr_impact  = _format_downstream(current_diagnosis.get("downstream_impact", []))
    curr_dataset = current_diagnosis.get("dataset_urn", "(unknown dataset)")

    return f"""You are a senior data engineering assistant helping to fix a schema break.

A similar incident ({past_id}) was resolved before. Your job is to ADAPT that
historical fix to fit the current incident's specific details.

----------------------------------------------------------------
PAST INCIDENT (id: {past_id})
----------------------------------------------------------------
Root cause: {past_root}

Resolution diff that was applied:
{past_diff}

----------------------------------------------------------------
CURRENT INCIDENT
----------------------------------------------------------------
Dataset          : {curr_dataset}
Root cause       : {curr_root}
Missing fields   : {curr_missing}
Type changes     : {curr_types}
Downstream impact: {curr_impact}

----------------------------------------------------------------
TASK
----------------------------------------------------------------
Adapt the historical resolution diff to address the CURRENT incident.

Instructions:
1. Start with a one-sentence summary of what changed.
2. Provide the adapted fix -- use a code diff, SQL DDL, or pipeline pseudocode
   as appropriate for the field names and types involved.
3. Call out any assumptions you make (e.g. "assuming the renamed column is X").
4. Keep your response concise and focused -- no unnecessary prose.
"""


def _build_fresh_prompt(diagnosis: Dict[str, Any]) -> str:
    """
    Prompt for the 'generated_fresh' mode: no past incident available;
    generate a fix from scratch using the current diagnosis.
    """
    root_cause     = diagnosis.get("root_cause", "(unknown)")
    missing_fields = _format_missing_fields(diagnosis.get("missing_fields", []))
    type_changes   = _format_type_changes(diagnosis.get("type_changes", []))
    downstream     = _format_downstream(diagnosis.get("downstream_impact", []))
    dataset_urn    = diagnosis.get("dataset_urn", "(unknown dataset)")
    confidence     = diagnosis.get("diagnosis_confidence") or diagnosis.get("confidence", "unknown")

    return f"""You are a senior data engineering assistant helping to fix a schema break.
No prior incident records match this situation closely enough to reuse -- you must
propose a fresh fix based on the current diagnosis alone.

----------------------------------------------------------------
CURRENT INCIDENT DIAGNOSIS
----------------------------------------------------------------
Dataset              : {dataset_urn}
Root cause           : {root_cause}
Missing fields       : {missing_fields}
Type changes         : {type_changes}
Downstream impact    : {downstream}
Diagnosis confidence : {confidence}

----------------------------------------------------------------
TASK
----------------------------------------------------------------
Propose a concrete fix for this schema break.

Instructions:
1. One-sentence summary of the break.
2. A concrete fix -- prefer:
   - A SQL/DDL snippet (ALTER TABLE, column alias, view definition), OR
   - A Python/Spark pipeline patch (pseudocode diff), OR
   - A DataHub schema update command
   ... whichever fits best given the field types mentioned.
3. Outline the migration steps in priority order (what to do first, second, ...).
4. Flag any downstream consumers that need immediate attention.
5. Keep your response concise and actionable -- no unnecessary prose.
"""


# ---------------------------------------------------------------------------
# Groq client factory
# ---------------------------------------------------------------------------

def _get_groq_client():
    """
    Return a Groq client instance.

    Uses the raw ``groq`` SDK directly (already installed) so we stay
    consistent with other AXIOM-pattern projects that call
    ``client.chat.completions.create()``.

    Raises
    ------
    RuntimeError
        If GROQ_API_KEY is not set in the environment.
    """
    try:
        from groq import Groq  # type: ignore
    except ImportError:
        raise RuntimeError(
            "groq package is not installed. Run: pip install groq"
        )

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            r"Add it to d:\Anamnesis\.env as: GROQ_API_KEY=gsk_..."
        )

    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Fixer Agent
# ---------------------------------------------------------------------------

class FixerAgent:
    """
    Generates a concrete fix suggestion for a detected schema break.

    Parameters
    ----------
    model : str
        Groq model name. Defaults to ``GROQ_MODEL`` env var or
        ``"llama-3.1-8b-instant"``.
    temperature : float
        LLM sampling temperature. Lower = more deterministic / precise.
        Defaults to ``GROQ_TEMPERATURE`` env var or ``0.3``.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ):
        self._model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
        self._temperature = (
            temperature
            if temperature is not None
            else float(os.getenv("GROQ_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
        )
        logger.info(
            "FixerAgent: model=%s  temperature=%.2f  threshold=%.2f",
            self._model, self._temperature, ADAPT_THRESHOLD,
        )

    # ---- Public entry point -------------------------------------------------

    def generate_fix(
        self,
        diagnosis: Dict[str, Any],
        recall_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate a fix suggestion for the current diagnosis.

        Parameters
        ----------
        diagnosis : dict
            Structured output from Diagnoser.diagnose().  Expected keys:
            ``root_cause``, ``missing_fields``, ``type_changes``,
            ``downstream_impact``, ``dataset_urn``.
        recall_result : dict
            Output from MemoryRecallAgent.recall_similar_incidents().
            Expected keys: ``matches`` (list), ``no_similar_incidents_found``.

        Returns
        -------
        dict -- see module docstring for full schema.
        """
        best_match = self._find_best_match(recall_result)

        if best_match is not None and best_match["similarity_score"] >= ADAPT_THRESHOLD:
            return self._generate_adapted(diagnosis, best_match)
        else:
            return self._generate_fresh(diagnosis)

    # ---- Private helpers ----------------------------------------------------

    def _find_best_match(
        self,
        recall_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Return the highest-scoring match, or None if no matches exist."""
        matches = recall_result.get("matches", [])
        if not matches:
            return None
        # matches are already sorted descending by similarity_score
        return matches[0]

    def _call_llm(self, prompt: str) -> str:
        """Send a prompt to Groq and return the text response."""
        client = _get_groq_client()
        logger.info(
            "FixerAgent: calling Groq API (model=%s, temp=%.2f, prompt_len=%d chars)",
            self._model, self._temperature, len(prompt),
        )
        response = client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert data engineer specialising in schema "
                        "migration, pipeline reliability, and DataHub lineage. "
                        "Respond with concise, actionable technical recommendations."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        text: str = response.choices[0].message.content or ""
        logger.info(
            "FixerAgent: received response (%d chars) from Groq",
            len(text),
        )
        return text.strip()

    def _generate_adapted(
        self,
        diagnosis: Dict[str, Any],
        best_match: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fast path: adapt a historical fix to the current context."""
        incident_id = best_match.get("incident_id", "?")
        similarity  = best_match.get("similarity_score", 0.0)
        time_saved  = best_match.get("time_saved_estimate")  # may be None or 0

        logger.info(
            "FixerAgent: mode=adapted  incident=%s  similarity=%.4f",
            incident_id, similarity,
        )

        prompt        = _build_adapt_prompt(diagnosis, best_match)
        suggested_fix = self._call_llm(prompt)

        confidence_note = (
            f"Adapted from past incident {incident_id} "
            f"(similarity score: {similarity:.2%}). "
            "The historical resolution diff was used as a template; "
            "review field names before applying."
        )

        return {
            "mode":                          "adapted",
            "suggested_fix":                 suggested_fix,
            "based_on_incident_id":          incident_id,
            "confidence_note":               confidence_note,
            "estimated_time_saved_minutes":  int(time_saved) if time_saved else None,
        }

    def _generate_fresh(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback path: generate a brand-new fix from the diagnosis alone."""
        logger.info(
            "FixerAgent: mode=generated_fresh (no high-similarity past incident found)"
        )

        prompt        = _build_fresh_prompt(diagnosis)
        suggested_fix = self._call_llm(prompt)

        confidence_note = (
            f"Generated fresh -- no past incident met the "
            f"{ADAPT_THRESHOLD:.0%} similarity threshold. "
            "Fix is based solely on the current diagnosis. "
            "Validate carefully before applying."
        )

        return {
            "mode":                          "generated_fresh",
            "suggested_fix":                 suggested_fix,
            "based_on_incident_id":          None,
            "confidence_note":               confidence_note,
            "estimated_time_saved_minutes":  None,
        }


# ---------------------------------------------------------------------------
# Module-level singleton + convenience function
# ---------------------------------------------------------------------------

_agent: Optional[FixerAgent] = None


def _get_agent() -> FixerAgent:
    global _agent
    if _agent is None:
        _agent = FixerAgent()
    return _agent


def generate_fix(
    diagnosis: Dict[str, Any],
    recall_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Module-level convenience wrapper around :class:`FixerAgent`.

    Uses a process-level singleton.  Import and call directly::

        from backend.agents.fixer import generate_fix
        result = generate_fix(diagnosis, recall_result)
    """
    return _get_agent().generate_fix(diagnosis, recall_result)
