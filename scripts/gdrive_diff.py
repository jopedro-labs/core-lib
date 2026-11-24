"""
Deterministic Structural Diff Engine for Google Drive API Discovery JSON.

Compares previous and current Google Drive v3 Discovery documents, extracts compact
structural deltas (methods, parameters, schemas, properties, types, enums),
and deterministically evaluates baseline impact level (LOW, MEDIUM, HIGH).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TypedDict

# Ensure workspace root is in sys.path when invoked directly
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

STATE_DIR = Path(".github/api-revisions")
DISCOVERY_FILE = STATE_DIR / "drive-v3-discovery.json"
PREVIOUS_DISCOVERY_FILE = STATE_DIR / "drive-v3-discovery.previous.json"


class ParameterModification(TypedDict, total=False):
    param: str
    change: str
    breaking: bool


class MethodParameterChange(TypedDict, total=False):
    method: str
    added_parameters: list[str]
    removed_parameters: list[str]
    modified_parameters: list[ParameterModification]


class PropertyModification(TypedDict, total=False):
    property: str
    change: str
    breaking: bool


class SchemaPropertyChange(TypedDict, total=False):
    schema: str
    added_properties: list[str]
    removed_properties: list[str]
    modified_properties: list[PropertyModification]


class DiscoveryDiffResult(TypedDict, total=False):
    impact_baseline: str
    methods_added: list[str]
    methods_removed: list[str]
    parameter_changes: list[MethodParameterChange]
    schemas_added: list[str]
    schemas_removed: list[str]
    schema_property_changes: list[SchemaPropertyChange]
    note: str
    error: str


def _flatten_methods(resources: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Recursively flattens API resources into a dictionary of method_id -> method_spec."""
    methods: dict[str, Any] = {}
    for res_name, res_val in resources.items():
        current_name = f"{prefix}.{res_name}" if prefix else res_name
        # Direct methods under resource
        for m_name, m_spec in res_val.get("methods", {}).items():
            methods[f"{current_name}.{m_name}"] = m_spec
        # Nested subresources
        if "resources" in res_val:
            methods.update(_flatten_methods(res_val["resources"], prefix=current_name))
    return methods


def compare_discovery_docs(
    prev_doc: dict[str, Any], curr_doc: dict[str, Any]
) -> DiscoveryDiffResult:
    """Compares two discovery documents and returns a compact structural delta."""
    prev_methods = _flatten_methods(prev_doc.get("resources", {}))
    curr_methods = _flatten_methods(curr_doc.get("resources", {}))

    methods_added: list[str] = sorted(list(set(curr_methods.keys()) - set(prev_methods.keys())))
    methods_removed: list[str] = sorted(list(set(prev_methods.keys()) - set(curr_methods.keys())))

    parameter_changes: list[MethodParameterChange] = []
    common_methods = set(curr_methods.keys()) & set(prev_methods.keys())

    for m_id in sorted(common_methods):
        prev_params = prev_methods[m_id].get("parameters", {})
        curr_params = curr_methods[m_id].get("parameters", {})

        added_p = set(curr_params.keys()) - set(prev_params.keys())
        removed_p = set(prev_params.keys()) - set(curr_params.keys())

        modified_p: list[ParameterModification] = []
        for p_name in set(curr_params.keys()) & set(prev_params.keys()):
            p_prev = prev_params[p_name]
            p_curr = curr_params[p_name]

            # 1. Required flag change
            prev_req = p_prev.get("required", False)
            curr_req = p_curr.get("required", False)
            if prev_req != curr_req:
                modified_p.append({
                    "param": p_name,
                    "change": f"required changed from {prev_req} to {curr_req}",
                    "breaking": (not prev_req and curr_req),
                })

            # 2. Type change
            prev_type = p_prev.get("type")
            curr_type = p_curr.get("type")
            if prev_type and curr_type and prev_type != curr_type:
                modified_p.append({
                    "param": p_name,
                    "change": f"type changed from '{prev_type}' to '{curr_type}'",
                    "breaking": True,
                })

            # 3. Enum restrictions / changes
            prev_enum = set(p_prev.get("enum", []))
            curr_enum = set(p_curr.get("enum", []))
            if prev_enum or curr_enum:
                removed_enum = prev_enum - curr_enum
                added_enum = curr_enum - prev_enum
                if removed_enum:
                    modified_p.append({
                        "param": p_name,
                        "change": f"enum values removed: {sorted(list(removed_enum))}",
                        "breaking": True,
                    })
                elif added_enum:
                    modified_p.append({
                        "param": p_name,
                        "change": f"enum values added: {sorted(list(added_enum))}",
                        "breaking": False,
                    })

        if added_p or removed_p or modified_p:
            parameter_changes.append({
                "method": m_id,
                "added_parameters": sorted(list(added_p)),
                "removed_parameters": sorted(list(removed_p)),
                "modified_parameters": modified_p,
            })

    # Schema changes
    prev_schemas = prev_doc.get("schemas", {})
    curr_schemas = curr_doc.get("schemas", {})

    schemas_added = sorted(list(set(curr_schemas.keys()) - set(prev_schemas.keys())))
    schemas_removed = sorted(list(set(prev_schemas.keys()) - set(curr_schemas.keys())))

    schema_property_changes: list[SchemaPropertyChange] = []
    for s_name in sorted(set(curr_schemas.keys()) & set(prev_schemas.keys())):
        prev_props = prev_schemas[s_name].get("properties", {})
        curr_props = curr_schemas[s_name].get("properties", {})

        added_props = set(curr_props.keys()) - set(prev_props.keys())
        removed_props = set(prev_props.keys()) - set(curr_props.keys())

        modified_props: list[PropertyModification] = []
        for prop_name in set(curr_props.keys()) & set(prev_props.keys()):
            type_prev = prev_props[prop_name].get("type")
            type_curr = curr_props[prop_name].get("type")
            ref_prev = prev_props[prop_name].get("$ref")
            ref_curr = curr_props[prop_name].get("$ref")

            if (type_prev and type_curr and type_prev != type_curr) or (ref_prev and ref_curr and ref_prev != ref_curr):
                modified_props.append({
                    "property": prop_name,
                    "change": f"type/$ref changed from '{type_prev or ref_prev}' to '{type_curr or ref_curr}'",
                    "breaking": True,
                })

        if added_props or removed_props or modified_props:
            schema_property_changes.append({
                "schema": s_name,
                "added_properties": sorted(list(added_props)),
                "removed_properties": sorted(list(removed_props)),
                "modified_properties": modified_props,
            })

    # Calculate deterministic impact level
    has_breaking = (
        bool(methods_removed)
        or bool(schemas_removed)
        or any(bool(p["removed_parameters"]) for p in parameter_changes)
        or any(any(m.get("breaking") for m in p["modified_parameters"]) for p in parameter_changes)
        or any(bool(sp["removed_properties"]) for sp in schema_property_changes)
        or any(any(mp.get("breaking") for mp in sp["modified_properties"]) for sp in schema_property_changes)
    )

    if has_breaking:
        impact = "HIGH"
    elif parameter_changes or schemas_added or schema_property_changes:
        impact = "MEDIUM"
    else:
        impact = "LOW"

    return {
        "impact_baseline": impact,
        "methods_added": methods_added,
        "methods_removed": methods_removed,
        "parameter_changes": parameter_changes,
        "schemas_added": schemas_added,
        "schemas_removed": schemas_removed,
        "schema_property_changes": schema_property_changes,
    }


def generate_diff_summary() -> DiscoveryDiffResult:
    """Loads documents from disk and generates the diff report."""
    if not PREVIOUS_DISCOVERY_FILE.exists() or not DISCOVERY_FILE.exists():
        return {
            "impact_baseline": "LOW",
            "methods_added": [],
            "methods_removed": [],
            "parameter_changes": [],
            "schemas_added": [],
            "schemas_removed": [],
            "schema_property_changes": [],
            "note": "Previous discovery document not available for structural diffing.",
        }

    try:
        prev_data = json.loads(PREVIOUS_DISCOVERY_FILE.read_text(encoding="utf-8"))
        curr_data = json.loads(DISCOVERY_FILE.read_text(encoding="utf-8"))
        return compare_discovery_docs(prev_data, curr_data)
    except Exception as e:
        return {
            "impact_baseline": "LOW",
            "methods_added": [],
            "methods_removed": [],
            "parameter_changes": [],
            "schemas_added": [],
            "schemas_removed": [],
            "schema_property_changes": [],
            "error": f"Failed to compute diff: {e}",
        }


def format_markdown_diff(diff: dict[str, Any]) -> str:
    """Formats the deterministic diff into a concise markdown section."""
    lines: list[str] = []

    has_changes = any([
        diff.get("methods_added"),
        diff.get("methods_removed"),
        diff.get("parameter_changes"),
        diff.get("schemas_added"),
        diff.get("schemas_removed"),
        diff.get("schema_property_changes"),
    ])

    if not has_changes:
        lines.append("No structural schema or parameter modifications detected. Changes are limited to documentation, descriptions, or internal metadata updates.")
        return "\n".join(lines)

    if diff.get("methods_added"):
        lines.append(f"- **Methods Added**: `{', '.join(diff['methods_added'])}`")
    if diff.get("methods_removed"):
        lines.append(f"- **🚨 Methods Removed**: `{', '.join(diff['methods_removed'])}`")

    if diff.get("schemas_added"):
        lines.append(f"- **Schemas Added**: `{', '.join(diff['schemas_added'])}`")
    if diff.get("schemas_removed"):
        lines.append(f"- **🚨 Schemas Removed**: `{', '.join(diff['schemas_removed'])}`")

    if diff.get("parameter_changes"):
        lines.append("- **Parameter Modifications**:")
        for item in diff["parameter_changes"]:
            m = item["method"]
            if item["added_parameters"]:
                lines.append(f"  - `{m}`: added optional `{', '.join(item['added_parameters'])}`")
            if item["removed_parameters"]:
                lines.append(f"  - `{m}`: 🚨 removed `{', '.join(item['removed_parameters'])}`")
            for mod in item.get("modified_parameters", []):
                prefix = "🚨 " if mod.get("breaking") else ""
                lines.append(f"  - `{m}`: {prefix}{mod['change']}")

    if diff.get("schema_property_changes"):
        lines.append("- **Schema Property Modifications**:")
        for item in diff["schema_property_changes"]:
            s = item["schema"]
            if item["added_properties"]:
                lines.append(f"  - `{s}`: added fields `{', '.join(item['added_properties'])}`")
            if item["removed_properties"]:
                lines.append(f"  - `{s}`: 🚨 removed fields `{', '.join(item['removed_properties'])}`")
            for mod in item.get("modified_properties", []):
                prefix = "🚨 " if mod.get("breaking") else ""
                lines.append(f"  - `{s}`: {prefix}{mod['change']}")

    return "\n".join(lines)


if __name__ == "__main__":
    diff_result = generate_diff_summary()
    print(json.dumps(diff_result, indent=2))
