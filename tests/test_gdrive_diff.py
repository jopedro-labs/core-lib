"""Unit tests for scripts/gdrive_diff.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.gdrive_diff import (
    _flatten_methods,
    compare_discovery_docs,
    format_markdown_diff,
    generate_diff_summary,
)


def test_flatten_methods_empty() -> None:
    assert _flatten_methods({}) == {}


def test_flatten_methods_nested() -> None:
    resources = {
        "files": {
            "methods": {
                "get": {"id": "drive.files.get"},
                "list": {"id": "drive.files.list"},
            },
            "resources": {
                "comments": {
                    "methods": {
                        "create": {"id": "drive.files.comments.create"}
                    }
                }
            },
        }
    }
    flattened = _flatten_methods(resources)
    assert "files.get" in flattened
    assert "files.list" in flattened
    assert "files.comments.create" in flattened


def test_compare_discovery_docs_identical() -> None:
    doc = {
        "resources": {
            "files": {
                "methods": {
                    "get": {
                        "parameters": {
                            "fileId": {"type": "string", "required": True}
                        }
                    }
                }
            }
        },
        "schemas": {
            "File": {
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                }
            }
        },
    }
    res = compare_discovery_docs(doc, doc)
    assert res["impact_baseline"] == "LOW"
    assert res["methods_added"] == []
    assert res["methods_removed"] == []
    assert res["parameter_changes"] == []
    assert res["schemas_added"] == []
    assert res["schemas_removed"] == []
    assert res["schema_property_changes"] == []


def test_compare_discovery_docs_added_and_removed_methods() -> None:
    prev_doc = {
        "resources": {
            "files": {
                "methods": {
                    "delete": {},
                    "get": {},
                }
            }
        }
    }
    curr_doc = {
        "resources": {
            "files": {
                "methods": {
                    "get": {},
                    "copy": {},
                }
            }
        }
    }
    res = compare_discovery_docs(prev_doc, curr_doc)
    assert res["methods_added"] == ["files.copy"]
    assert res["methods_removed"] == ["files.delete"]
    # Removal is breaking -> HIGH impact
    assert res["impact_baseline"] == "HIGH"


def test_compare_discovery_docs_parameter_changes() -> None:
    prev_doc = {
        "resources": {
            "files": {
                "methods": {
                    "list": {
                        "parameters": {
                            "q": {"type": "string"},
                            "deprecatedParam": {"type": "string"},
                            "status": {"type": "string", "enum": ["A", "B", "C"]},
                            "filter": {"type": "string", "required": False},
                        }
                    }
                }
            }
        }
    }
    curr_doc = {
        "resources": {
            "files": {
                "methods": {
                    "list": {
                        "parameters": {
                            "q": {"type": "string"},
                            "newParam": {"type": "string"},
                            "status": {"type": "string", "enum": ["A", "B"]},  # enum removed
                            "filter": {"type": "string", "required": True},  # required changed -> breaking
                        }
                    }
                }
            }
        }
    }
    res = compare_discovery_docs(prev_doc, curr_doc)
    assert len(res["parameter_changes"]) == 1
    p_change = res["parameter_changes"][0]
    assert p_change["method"] == "files.list"
    assert "newParam" in p_change["added_parameters"]
    assert "deprecatedParam" in p_change["removed_parameters"]
    assert res["impact_baseline"] == "HIGH"


def test_compare_discovery_docs_parameter_type_and_enum_add() -> None:
    prev_doc = {
        "resources": {
            "files": {
                "methods": {
                    "get": {
                        "parameters": {
                            "version": {"type": "integer"},
                            "mode": {"type": "string", "enum": ["read"]},
                        }
                    }
                }
            }
        }
    }
    curr_doc = {
        "resources": {
            "files": {
                "methods": {
                    "get": {
                        "parameters": {
                            "version": {"type": "string"},  # type changed -> breaking
                            "mode": {"type": "string", "enum": ["read", "write"]},  # enum added -> non-breaking
                        }
                    }
                }
            }
        }
    }
    res = compare_discovery_docs(prev_doc, curr_doc)
    assert res["impact_baseline"] == "HIGH"
    mods = res["parameter_changes"][0]["modified_parameters"]
    version_mod = next(m for m in mods if m["param"] == "version")
    assert version_mod["breaking"] is True
    mode_mod = next(m for m in mods if m["param"] == "mode")
    assert mode_mod["breaking"] is False


def test_compare_discovery_docs_schemas() -> None:
    prev_doc = {
        "schemas": {
            "OldSchema": {},
            "ExistingSchema": {
                "properties": {
                    "oldField": {"type": "string"},
                    "changedField": {"type": "string"},
                }
            },
        }
    }
    curr_doc = {
        "schemas": {
            "NewSchema": {},
            "ExistingSchema": {
                "properties": {
                    "newField": {"type": "string"},
                    "changedField": {"type": "integer"},
                }
            },
        }
    }
    res = compare_discovery_docs(prev_doc, curr_doc)
    assert res["schemas_added"] == ["NewSchema"]
    assert res["schemas_removed"] == ["OldSchema"]
    assert res["impact_baseline"] == "HIGH"


def test_compare_discovery_docs_medium_baseline() -> None:
    prev_doc = {
        "schemas": {
            "ExistingSchema": {
                "properties": {
                    "field1": {"type": "string"},
                }
            }
        }
    }
    curr_doc = {
        "schemas": {
            "ExistingSchema": {
                "properties": {
                    "field1": {"type": "string"},
                    "field2": {"type": "string"},  # added property -> non breaking
                }
            },
            "AddedSchema": {},  # added schema -> non breaking
        }
    }
    res = compare_discovery_docs(prev_doc, curr_doc)
    assert res["impact_baseline"] == "MEDIUM"
    assert res["schemas_added"] == ["AddedSchema"]


def test_format_markdown_diff_empty() -> None:
    diff = {
        "impact_baseline": "LOW",
        "methods_added": [],
        "methods_removed": [],
        "parameter_changes": [],
        "schemas_added": [],
        "schemas_removed": [],
        "schema_property_changes": [],
    }
    md = format_markdown_diff(diff)
    assert "No structural schema or parameter modifications detected" in md


def test_format_markdown_diff_populated() -> None:
    diff = {
        "impact_baseline": "HIGH",
        "methods_added": ["files.copy"],
        "methods_removed": ["files.delete"],
        "schemas_added": ["NewSchema"],
        "schemas_removed": ["OldSchema"],
        "parameter_changes": [
            {
                "method": "files.list",
                "added_parameters": ["pageSize"],
                "removed_parameters": ["maxResults"],
                "modified_parameters": [
                    {"param": "q", "change": "type changed", "breaking": True}
                ],
            }
        ],
        "schema_property_changes": [
            {
                "schema": "File",
                "added_properties": ["shortcutDetails"],
                "removed_properties": ["obsoleteDetails"],
                "modified_properties": [
                    {"property": "mimeType", "change": "type changed", "breaking": True}
                ],
            }
        ],
    }
    md = format_markdown_diff(diff)
    assert "Methods Added" in md
    assert "Methods Removed" in md
    assert "Schemas Added" in md
    assert "Schemas Removed" in md
    assert "Parameter Modifications" in md
    assert "Schema Property Modifications" in md


def test_generate_diff_summary_missing_files(tmp_path) -> None:
    with patch("scripts.gdrive_diff.PREVIOUS_DISCOVERY_FILE", tmp_path / "missing1.json"):
        with patch("scripts.gdrive_diff.DISCOVERY_FILE", tmp_path / "missing2.json"):
            res = generate_diff_summary()
            assert res["impact_baseline"] == "LOW"
            assert "note" in res


def test_generate_diff_summary_corrupted_file(tmp_path) -> None:
    f1 = tmp_path / "prev.json"
    f2 = tmp_path / "curr.json"
    f1.write_text("invalid json")
    f2.write_text("{}")
    with patch("scripts.gdrive_diff.PREVIOUS_DISCOVERY_FILE", f1):
        with patch("scripts.gdrive_diff.DISCOVERY_FILE", f2):
            res = generate_diff_summary()
            assert res["impact_baseline"] == "LOW"
            assert "error" in res
