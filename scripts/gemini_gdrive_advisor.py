"""
Gemini Google Drive API Revision Advisor Agent.

Analyzes deterministic API structural diffs against local core_lib.gdrive implementation,
consults Gemini API using the modern google-genai SDK for semantic impact,
and generates a refined GitHub Issue Markdown report.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path when invoked directly
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.gdrive_diff import format_markdown_diff, generate_diff_summary

STATE_FILE = Path(".github/api-revisions/gdrive-revision.json")
PREVIOUS_STATE_FILE = Path(".github/api-revisions/gdrive-revision.previous.json")
REPORT_PATH = Path("reports/gdrive_revision_analysis.md")
DEFAULT_MODEL = "gemini-2.5-flash"
TIMEOUT_SECONDS = 20.0


def scan_local_gdrive_usage() -> list[str]:
    """Scans core_lib/gdrive for active Drive API method calls."""
    gdrive_dir = Path("core_lib/gdrive")
    if not gdrive_dir.exists():
        return ["files().get", "files().list", "files().create", "files().update", "files().get_media"]

    detected_calls: set[str] = set()
    patterns = [
        "service.files().get",
        "service.files().list",
        "service.files().create",
        "service.files().update",
        "service.files().delete",
        "service.files().get_media",
        "service.about().get",
        "service.permissions()",
    ]

    for py_file in gdrive_dir.glob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            for pattern in patterns:
                call_clean = pattern.replace("service.", "")
                if call_clean in content or pattern in content:
                    detected_calls.add(call_clean)
        except Exception:
            continue

    return sorted(list(detected_calls)) if detected_calls else ["files().list", "files().get", "files().create"]


def query_gemini(
    diff_data: dict[str, Any],
    local_methods: list[str],
    prev_rev: str,
    curr_rev: str,
) -> tuple[str, str, str]:
    """Queries Gemini API using the official modern google-genai SDK with explicit timeout.

    Returns:
        tuple of (impact_level, summary, markdown_analysis)
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not configured.")

    from google import genai
    from google.genai import types

    # Initialize client with explicit 20s timeout configuration
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS),
    )
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    prompt = f"""
You are the Google Drive API Revision Advisor Agent for 'core-lib'.
Analyze the following verified structural diff between Google Drive API v3 revisions:
Previous Revision: {prev_rev}
Current Revision: {curr_rev}

Verified Structural Diff (Ground Truth):
{json.dumps(diff_data, indent=2)}

Google Drive API methods actively used in this repository (`core_lib/gdrive/`):
{json.dumps(local_methods, indent=2)}

Ground-truth & Anti-hallucination rules:
1. Base your assessment ONLY on the changes present in the diff above. DO NOT invent or assume changes that are not in the diff.
2. If the diff has no methods, parameters, or schemas changed, impact MUST be 'LOW' (Documentation/Metadata update only).
3. Evaluate if any modified/removed methods or parameters overlap with the actively used methods in this repository.
4. Select impact_level strictly as one of: [LOW, MEDIUM, HIGH].
5. Provide a single-line summary (max 120 chars).

Output your response strictly as a JSON object with this exact structure:
{{
  "impact_level": "LOW|MEDIUM|HIGH",
  "summary": "Concise single line explanation",
  "codebase_impact_analysis": "2-3 paragraphs analyzing compatibility with core_lib.gdrive",
  "action_checklist": [
    "Checklist item 1",
    "Checklist item 2"
  ]
}}
"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    parsed = json.loads(text)
    impact = str(parsed.get("impact_level", diff_data.get("impact_baseline", "LOW"))).upper()
    if impact not in {"LOW", "MEDIUM", "HIGH"}:
        impact = diff_data.get("impact_baseline", "LOW")

    summary = str(parsed.get("summary", f"Revision changed from {prev_rev} to {curr_rev}"))

    analysis_parts = [
        parsed.get("codebase_impact_analysis", "Review verified against active repository endpoints."),
        "",
        "#### Recommended Actions:",
    ]
    for item in parsed.get("action_checklist", ["Review Google Drive API changelog", "Run test suite"]):
        analysis_parts.append(f"- [ ] {item}")

    return impact, summary, "\n".join(analysis_parts)


def resolve_impact_level(baseline_impact: str, gemini_impact: str) -> str:
    """Enforces strict ceiling rule on impact_level:
    - If baseline is LOW (metadata or benign additions), impact can NEVER exceed LOW.
    - If baseline is MEDIUM, impact can be downgraded to LOW (if unused) or stay MEDIUM, but cannot jump to HIGH.
    - If baseline is HIGH, impact can stay HIGH or be downgraded to LOW/MEDIUM based on repository exposure.
    """
    severity_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    baseline_val = severity_order.get(baseline_impact, 1)

    if baseline_val == 1:
        # LOW is authoritative floor and ceiling when diff has no structural breaking changes
        return "LOW"
    elif baseline_val == 2:
        # Cap at MEDIUM: Gemini can keep MEDIUM or downgrade to LOW if methods are unused
        return "LOW" if gemini_impact == "LOW" else "MEDIUM"
    else:
        # HIGH baseline: can be HIGH, or downgraded to MEDIUM/LOW if codebase has zero exposure
        return gemini_impact if gemini_impact in severity_order else "HIGH"


def build_markdown_report(
    prev_rev: str,
    curr_rev: str,
    impact_level: str,
    summary: str,
    analysis_status: str,
    diff_markdown: str,
    ai_evaluation: str,
    run_id: str,
    model_name: str,
) -> str:
    """Builds the final Markdown report compliant with GDRIVE_BOT.md template."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_label = (
        f"Full AI Analysis ({model_name})"
        if analysis_status == "ok"
        else "Fallback (Deterministic Diff Only)"
    )

    return f"""## 📋 Google Drive API Revision Changed: `{prev_rev}` ➔ `{curr_rev}`

### 1. Executive Summary
- **Detected At**: `{now_utc}`
- **Impact Level**: `{impact_level}`
- **Analysis Status**: `{status_label}`
- **Summary**: {summary}

### 2. Verified API Schema Changes (Deterministic Diff)
{diff_markdown}

### 3. Impact Assessment on `core_lib.gdrive`
{ai_evaluation}

---
*Generated by Gemini GDrive Advisor Agent ({model_name}) via GitHub Actions Run #{run_id}*
"""


def write_github_output(key: str, value: str) -> None:
    """Writes output key/value pair to $GITHUB_OUTPUT using EOF delimiter for multiline safety."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        delimiter = f"EOF_{uuid.uuid4().hex}"
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def main() -> None:
    """Entry point for the Gemini GDrive Advisor."""
    print("🔍 Computing deterministic API structural diff...")
    diff_data = generate_diff_summary()
    diff_markdown = format_markdown_diff(diff_data)
    baseline_impact = diff_data.get("impact_baseline", "LOW")

    # Load revisions safely
    prev_rev = "unknown"
    curr_rev = "unknown"
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            curr_rev = state.get("revision", "unknown")
        except Exception:
            pass

    if PREVIOUS_STATE_FILE.exists():
        try:
            prev_state = json.loads(PREVIOUS_STATE_FILE.read_text(encoding="utf-8"))
            prev_rev = prev_state.get("revision", prev_rev)
        except Exception:
            pass

    if prev_rev == "unknown":
        prev_rev = os.environ.get("PREVIOUS_REVISION", "unknown")
    if curr_rev == "unknown":
        curr_rev = os.environ.get("CURRENT_REVISION", "unknown")

    local_methods = scan_local_gdrive_usage()
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")

    impact_level = baseline_impact
    analysis_status = "fallback_diff_only"
    summary = f"API revision updated to {curr_rev} (Baseline Impact: {baseline_impact})"

    ai_evaluation = f"""- **Monitored Methods Used in Repo**: `{', '.join(local_methods)}`
- **Potential Breaking Risk**: `{'High' if baseline_impact == 'HIGH' else ('Low' if baseline_impact == 'MEDIUM' else 'None')}`
- **Note**: Deterministic fallback used. Please review diff directly.

#### Developer Action Checklist
- [ ] Review Google Drive API official changelog.
- [ ] Run test suite: `pytest tests/test_gdrive*`.
- [ ] Verify existing methods against schema property modifications.
"""

    # Try Gemini Enrichment
    try:
        print(f"🤖 Consulting Gemini ({model_name}) via google-genai for semantic evaluation...")
        gemini_impact, gemini_summary, gemini_eval = query_gemini(
            diff_data=diff_data,
            local_methods=local_methods,
            prev_rev=prev_rev,
            curr_rev=curr_rev,
        )

        # Enforce strict ceiling authority rule
        impact_level = resolve_impact_level(baseline_impact, gemini_impact)
        summary = gemini_summary
        ai_evaluation = gemini_eval
        analysis_status = "ok"
        print(f"✅ Gemini evaluation complete. Resolved impact: {impact_level} (Baseline: {baseline_impact})")

    except Exception as e:
        print(f"⚠️ Gemini enrichment unavailable or failed: {e}. Using deterministic fallback.")
        analysis_status = "fallback_diff_only"
        impact_level = baseline_impact

    # Build and write report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_content = build_markdown_report(
        prev_rev=prev_rev,
        curr_rev=curr_rev,
        impact_level=impact_level,
        summary=summary,
        analysis_status=analysis_status,
        diff_markdown=diff_markdown,
        ai_evaluation=ai_evaluation,
        run_id=run_id,
        model_name=model_name,
    )
    REPORT_PATH.write_text(report_content, encoding="utf-8")
    print(f"📄 Report written to {REPORT_PATH}")

    # Export to GITHUB_OUTPUT with safe delimiters
    write_github_output("impact_level", impact_level)
    write_github_output("analysis_status", analysis_status)
    write_github_output("summary", summary.replace("\n", " ").strip())
    write_github_output("report_file", str(REPORT_PATH))


if __name__ == "__main__":
    main()
