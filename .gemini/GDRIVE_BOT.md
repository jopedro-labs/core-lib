# Google Drive API Revision Advisor Agent (Gemini)

## Objective
This autonomous agent analyzes Google Drive API revision changes detected during the `gdrive_bot.yml` workflow execution in the **`core-lib`** repository. 

To eliminate AI hallucinations, false positives, and diverging evaluations, the agent operates on **ground truth data**: it first computes a compact, deterministic structural diff between the previous and current Google Drive v3 Discovery documents (schemas, endpoints, parameters, and properties). The deterministic diff establishes the **authoritative structural baseline**, while Gemini refines and contextualizes the impact strictly on the methods used in `core_lib/gdrive/` to generate a high-signal GitHub Issue and an aligned Discord alert.

---

## Core Principles & Decision Authority Rules

1. **Deterministic Baseline as Authoritative Floor (No Hallucinated Severity)**:
   - The deterministic engine (`scripts/gdrive_diff.py`) evaluates the structural delta:
     - `LOW`: No structural changes (metadata/doc updates only) or non-breaking additive fields.
     - `MEDIUM`: Deprecations, optional parameter changes, or behavioral flags.
     - `HIGH`: Breaking changes (removed methods, removed parameters, required field additions).
   - **Precedence Rule**:
     - If the deterministic baseline is `LOW` (pure metadata or benign additions), the LLM **cannot** elevate it to `HIGH`.
     - The Gemini advisor can only adjust severity within strict bounds:
       - May upgrade `LOW` to `MEDIUM` if an added field/flag directly affects an active workflow in `core_lib/gdrive/`.
       - May downgrade `HIGH` or `MEDIUM` to `LOW` if the modified/removed endpoint is completely absent from `core_lib/gdrive/` (zero codebase exposure).
     - The advisor script enforces these guardrails and exports a **single, resolved `impact_level`** to `$GITHUB_OUTPUT`.

2. **Compact Diff & Prompt Token Budget**:
   - The full Discovery document is large (~150KB+ JSON). Sending entire JSONs risks hitting timeouts and inflating latency.
   - The diff engine (`scripts/gdrive_diff.py`) extracts **only structural deltas** (added/removed/modified endpoints, parameters, schema properties) into a compact JSON (~2-5KB).
   - Only this compact delta plus relevant API call signatures extracted from `core_lib/gdrive/` are sent in the Gemini prompt.

3. **Clear Separation of Facts vs Inferences**:
   - The generated report explicitly distinguishes:
     - **Verified Schema Diff (Deterministic Fact)**: Added/removed methods, fields, parameters.
     - **AI Impact Assessment (Hypothesis/Review)**: How these specific changes map to existing methods in `core_lib/gdrive/` (`files().list`, `files().create`, `about().get`, etc.).

4. **Strict Scope Separation**:
   - Execution errors (`result == 'error'`, network/DNS timeouts, HTTP 5xx) are **infrastructure issues** and bypass the Gemini advisor.
   - The Gemini agent is invoked **only** on `result == 'revision_changed'`.

5. **Single Source of Truth**:
   - The final resolved `impact_level` (`LOW`, `MEDIUM`, `HIGH`) and executive summary are calculated once and shared across GitHub Issues and Discord notifications.

---

## Architecture & Workflow Execution Sequence

To prevent duplicate issues and broken state, the execution order enforces:
1. **State Persistence First (with Rebase/Retry)**: Commits the new revision and discovery doc to `bot-state` immediately after analysis. If state persistence fails, the workflow aborts before opening an issue, preventing duplicate alerts on the next scheduled run.
2. **Issue Creation Second**: Creates the GitHub Issue with the verified state and analysis.
3. **Discord Notification Last (Non-blocking)**: Sends the webhook notification. Failures in Discord delivery do not affect state consistency or issue creation.

```
[State Restoration]
  └─ Restores `.github/api-revisions/drive-v3-discovery.json` from `origin/bot-state`
         │
         ▼
[Discovery Check: scripts/gdrive_update_bot.py]
  ├─ Fetches current Discovery JSON from Google
  ├─ Detects revision change (sys.exit 2, result='revision_changed')
  └─ Writes current Discovery document to disk (runner ephemeral storage)
         │
         ▼ (only if result == 'revision_changed')
[Deterministic Diff Engine: scripts/gdrive_diff.py]
  ├─ Compares Previous vs Current Discovery JSON
  ├─ Emits compact structural delta JSON (facts only, filtered for size)
  └─ Calculates baseline deterministic impact (LOW, MEDIUM, HIGH)
         │
         ▼
[Gemini Revision Advisor: scripts/gemini_gdrive_advisor.py]
  ├─ Scans `core_lib/gdrive/` for API call signatures
  ├─ Calls Gemini API ($GEMINI_MODEL) with 20s timeout
  ├─ Applies authority rules (reconciles deterministic baseline vs Gemini assessment)
  ├─ Outputs final markdown report (`reports/gdrive_revision_analysis.md`)
  └─ Exports outputs to $GITHUB_OUTPUT (impact_level, summary, analysis_status)
         │
         ▼
[State Persistence to `bot-state` (Critical Gate)]
  ├─ Switches to `bot-state` branch
  ├─ Updates `drive-v3-discovery.json` and `gdrive-revision.json`
  ├─ Performs git push with rebase retry loop (up to 3 attempts)
  └─ If push fails: pipeline aborts (no duplicate issue created)
         │
         ▼
[GitHub Issue Created]
  └─ Creates issue using the generated report and labels
         │
         ▼
[Discord Notification Sent (Non-blocking)]
  └─ Dispatches alert matching issue impact_level (failures logged, won't fail job)
```

---

## Inputs & Contextual Artifacts (All within `core-lib`)

1. **State Files** (persisted on `bot-state` branch):
   - `.github/api-revisions/gdrive-revision.json`: Previous metadata (`revision`, `version`, `title`).
   - `.github/api-revisions/drive-v3-discovery.json`: Previous full Discovery document.
2. **Current Discovery Document**:
   - Fetched live from `https://www.googleapis.com/discovery/v1/apis/drive/v3/rest`.
3. **Target Codebase (`core_lib/gdrive/`)**:
   - `core_lib/gdrive/gdrive_service.py`
   - `core_lib/gdrive/gdrive_helpers.py`
   - `core_lib/gdrive/gdrive_auth.py`
4. **Transient Runner Artifacts**:
   - Generated reports reside under `reports/` (e.g. `reports/gdrive_revision_analysis.md`), which is listed in `.gitignore` to avoid unintended dirty working directory states.

---

## Output Contract & Template

### 1. GitHub Output Variables (`$GITHUB_OUTPUT`)

| Output Key | Allowed Values | Description | Authority / Fallback Behavior |
|---|---|---|---|
| `impact_level` | `LOW` \| `MEDIUM` \| `HIGH` | Uniform classification across GitHub Issue and Discord alert. | Deterministic baseline constrained by Gemini codebase analysis. In fallback: pure deterministic baseline. |
| `analysis_status` | `ok` \| `fallback_diff_only` | Indicates whether Gemini enriched the issue or if fallback was used. | Set to `fallback_diff_only` if Gemini fails or times out. |
| `summary` | string (single-line) | Concise explanation of changes and impact. | Generated by Gemini or template-derived on fallback. |
| `report_file` | string (path) | Path to generated markdown report in runner workspace. | Points to `reports/gdrive_revision_analysis.md`. |

### 2. GitHub Issue Structure

```markdown
## 📋 Google Drive API Revision Changed: `{PREVIOUS_REVISION}` ➔ `{CURRENT_REVISION}`

### 1. Executive Summary
- **Detected At**: `YYYY-MM-DD HH:MM:SS UTC`
- **Impact Level**: `[LOW | MEDIUM | HIGH]`
- **Analysis Status**: `[Full AI Analysis (Gemini) | Fallback (Deterministic Diff Only)]`
- **Summary**: Concise description of what changed.

### 2. Verified API Schema Changes (Deterministic Diff)
- **Methods Added/Changed/Removed**:
  - `files.list`: Added optional parameter `includeItemsFromAllDrives` (example).
- **Schemas / Fields Modified**:
  - `File`: Added field `sha256Checksum` (read-only) (example).
- *(If no functional changes were detected)*: "No schema or parameter modifications detected. Changes are limited to documentation or metadata updates."

### 3. Impact Assessment on `core_lib.gdrive` (AI Evaluation)
- **Monitored Methods Used in Repo**: (e.g. `files().get`, `files().create`, `files().list`, `about().get`).
- **Potential Breaking Risk**: `None | Low | High` (with rationale grounded strictly in the diff).
- **Affected Files**: e.g., `core_lib/gdrive/gdrive_service.py` if an altered method is called there.

### 4. Developer Action Checklist
- [ ] Review Google Drive API official changelog.
- [ ] Run test suite: `pytest tests/test_gdrive*`.
- [ ] (If applicable) Evaluate adopting newly exposed fields.

---
*Generated by Gemini GDrive Advisor Agent (${GEMINI_MODEL}) via GitHub Actions Run #${RUN_ID}*
```

### 3. Discord Notification Alignment & Non-blocking Policy
The Discord step consumes the uniform outputs exported by the agent. If the webhook fails (HTTP 4xx/5xx or secret unset), a warning is logged, but the workflow step completes successfully (`continue-on-error: true` or soft-exit), ensuring notification outages do not block pipeline execution:
```text
📋 **Google Drive API Monitor** [Impact: HIGH]: Breaking change detected in files.list query parameters.
🔗 Issue: https://github.com/jopedro-labs/core-lib/issues/123 | Run: https://...
```

---

## Configuration & Environment Variables

| Variable | Scope | Description | Default |
|---|---|---|---|
| `GEMINI_API_KEY` | Secret | API key to access Google Gemini API. | *Required for AI analysis* |
| `GEMINI_MODEL` | Var / Env | Gemini model name to use for reasoning. | `gemini-2.5-flash` |
| `GITHUB_OUTPUT` | Action Env | Runner environment file for exporting outputs. | Automatically set |
| `INFRA_ALERTS_DISCORD_WEBHOOK` | Secret | Discord Webhook URL for notifications. | Optional |

---

## State Persistence & Concurrency Strategy

1. **State Persistence Gate**:
   - State commit and push to `bot-state` happens **before** opening GitHub Issues.
   - Push uses a rebase-retry loop (`git pull --rebase origin bot-state && git push origin bot-state`) with up to 3 retries to handle concurrent or stale branch references.
   - If state persistence fails, the workflow terminates immediately. No orphan issues are opened, preventing duplicate issues on subsequent scheduled runs.

2. **Resilience & Graceful Fallbacks**:
   - If `GEMINI_API_KEY` is missing, invalid, or the API call times out (>20s):
     - `analysis_status` is set to `fallback_diff_only`.
     - `impact_level` defaults strictly to the deterministic baseline (`LOW`, `MEDIUM`, or `HIGH`).
     - The issue body is built from the deterministic diff table directly, without breaking downstream steps.
   - Network/DNS execution errors (`sys.exit 1` in discovery check) bypass Gemini and state persistence, routing directly to the standard infrastructure failure alert.
