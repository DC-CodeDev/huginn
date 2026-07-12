"""Tests unitarios para validación MCP estricta de nodos."""

import pytest
from pydantic import ValidationError

from app.mcp.node_validation import validate_update_changes
from app.services.errors import ValidationFailure


def test_validate_update_changes_card_success():
    payload, changed_fields = validate_update_changes(
        "card",
        {
            "title": "Nuevo",
            "tags": ["a"],
            "blocks": [],
        },
    )
    assert payload.title == "Nuevo"
    assert payload.tags == ["a"]
    assert payload.blocks == []
    assert changed_fields == ["title", "tags", "blocks"]


def test_validate_update_changes_rejects_empty_changes():
    with pytest.raises(ValidationFailure, match="Debe especificar al menos un cambio"):
        validate_update_changes("card", {})


def test_validate_update_changes_rejects_card_orientation():
    with pytest.raises(ValidationError):
        validate_update_changes("card", {"orientation": "vertical"})


def test_validate_update_changes_rejects_timeline_blocks():
    with pytest.raises(ValidationError):
        validate_update_changes("timeline", {"blocks": []})


def test_validate_update_changes_rejects_invalid_orientation():
    with pytest.raises(ValidationError):
        validate_update_changes("timeline", {"orientation": "diagonal"})
