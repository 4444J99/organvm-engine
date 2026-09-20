"""Nullable revenue schema policy must retain accepted source provenance."""

import hashlib
import json
import warnings

import pytest

from organvm_engine.registry.validator import capture_registry_validation_policy


@pytest.mark.parametrize("key", ["revenue_model", "revenue_status"])
@pytest.mark.parametrize("declared_type", [["string", "null"], ["null", "string"]])
def test_nullable_string_enum_retains_external_policy(tmp_path, key, declared_type):
    schema = {
        "$defs": {
            "repository": {
                "properties": {
                    key: {"type": declared_type, "enum": ["assessed", None]},
                },
            },
        },
    }
    source = tmp_path / "registry-v2.schema.json"
    payload = (json.dumps(schema) + "\n").encode()
    source.write_bytes(payload)
    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter("always")
        policy = capture_registry_validation_policy((source,))
    assert not observed
    assert policy.source_kind == "external-schema"
    assert policy.source_sha256 == "sha256:" + hashlib.sha256(payload).hexdigest()
    choices = policy.revenue_models if key == "revenue_model" else policy.revenue_statuses
    assert choices == frozenset({"assessed"})
    assert source.read_bytes() == payload
    # Receipt evidence remains deterministic JSON with no mixed-type sorting.
    json.dumps(policy.evidence(), sort_keys=True)


@pytest.mark.parametrize("declared_type", [None, "string", ["string"], ["integer", "null"]])
def test_undeclared_or_nonstring_null_still_falls_back(tmp_path, declared_type):
    source = tmp_path / "registry-v2.schema.json"
    source.write_text(
        json.dumps(
            {
                "$defs": {
                    "repository": {
                        "properties": {
                            "revenue_model": {"type": declared_type, "enum": ["internal", None]},
                        },
                    },
                },
            },
        ),
    )
    with pytest.warns(UserWarning, match="Failed to parse"):
        policy = capture_registry_validation_policy((source,))
    assert policy.source_kind == "embedded-fallback"


@pytest.mark.parametrize("bad", [False, 7, "", {}, []])
def test_nullable_enum_does_not_accept_other_malformed_choices(tmp_path, bad):
    source = tmp_path / "registry-v2.schema.json"
    source.write_text(
        json.dumps(
            {
                "$defs": {
                    "repository": {
                        "properties": {
                            "revenue_status": {
                                "type": ["string", "null"],
                                "enum": ["live", None, bad],
                            },
                        },
                    },
                },
            },
        ),
    )
    with pytest.warns(UserWarning, match="Failed to parse"):
        policy = capture_registry_validation_policy((source,))
    assert policy.source_kind == "embedded-fallback"
