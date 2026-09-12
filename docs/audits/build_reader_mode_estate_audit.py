"""Build and execute the reader-mode estate audit notebook.

The seven source inventories are transient, authorized audit exports held outside
the public repository because they include private-repository names. Generated
artifacts contain aggregate private counts and public-repository rows only.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import secrets
import stat
import tempfile
import tokenize
import traceback
from contextlib import contextmanager, suppress
from pathlib import Path
from textwrap import dedent

import nbformat
from nbclient import NotebookClient

from organvm_engine.documentation.privacy import (
    PUBLIC_EXACT_REWRITES,
    PUBLIC_PROSE_REWRITES,
    private_only_repository_slugs,
    repository_reference_pattern,
)

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "2026-08-31-reader-mode-estate-audit.ipynb"
INPUT_MANIFEST = HERE / "reader-mode-input-manifest.json"
PUBLISHED_ARTIFACT_NAMES = (
    NOTEBOOK.name,
    "reader-mode-estate-summary.json",
    "reader-mode-public-rollout.json",
    "reader-mode-estate-audit.md",
)
MAX_PUBLICATION_ARTIFACT_BYTES = 64_000_000
ARTIFACT_RECOVERY_NAME = ".reader-mode-publication.recovery"
MAX_ARTIFACT_RECOVERY_BYTES = 64_000
SOURCE_FILES = {
    "personal": "personal.json",
    "ergon": "ergon.json",
    "theoria_poiesis": "theoria-poiesis.json",
    "governance_comms": "governance-comms.json",
    "umbrella_core": "umbrella-core.json",
    "umbrella_extended": "umbrella-extended.json",
    "organvm_gap": "organvm-gap.json",
}


def audit_input_dir() -> Path:
    """Resolve the separately retained authorized export directory."""
    configured = os.environ.get("ORGANVM_DOC_AUDIT_INPUT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (HERE / "../../../audit").resolve()


def source_visibility(row: dict, *, source: str, index: int) -> str:
    """Resolve a source row's visibility without guessing malformed values."""
    visibility = row.get("visibility")
    if visibility in {"public", "private"}:
        return visibility
    if visibility is not None:
        raise RuntimeError(f"{source} row {index} has invalid visibility: {visibility!r}")
    public = row.get("metadata", {}).get("public")
    if isinstance(public, bool):
        return "public" if public else "private"
    raise RuntimeError(f"{source} row {index} has no valid visibility")


def source_archived(row: dict, *, source: str, index: int) -> bool:
    """Resolve archived state without coercing malformed values to truthiness."""
    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        raise RuntimeError(f"{source} row {index} has invalid metadata")
    value = row.get("archived", metadata.get("archived", False))
    if not isinstance(value, bool):
        raise RuntimeError(f"{source} row {index} has invalid archived value: {value!r}")
    return value


def verify_live_inputs_against_manifest() -> tuple[
    dict,
    bytes,
    dict[str, bytes],
    dict[str, dict],
]:
    """Return the pinned manifest, exact bytes, source snapshots, and parsed bundles."""
    try:
        manifest_bytes = INPUT_MANIFEST.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read pinned input manifest: {INPUT_MANIFEST.name}") from exc

    if manifest.get("schema_version") != "reader-mode-input-manifest.v1":
        raise RuntimeError("Pinned input manifest has an unsupported schema version")
    declared_sources = manifest.get("sources")
    if not isinstance(declared_sources, list):
        raise RuntimeError("Pinned input manifest sources must be a list")
    by_segment: dict[str, dict] = {}
    for entry in declared_sources:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_segment"), str):
            raise RuntimeError("Pinned input manifest contains an invalid source entry")
        segment = entry["source_segment"]
        if segment in by_segment:
            raise RuntimeError(f"Pinned input manifest repeats source segment {segment!r}")
        by_segment[segment] = entry
    if set(by_segment) != set(SOURCE_FILES):
        raise RuntimeError("Pinned input manifest source segments do not match the builder")

    live_totals = {
        "source_segments": len(SOURCE_FILES),
        "repositories": 0,
        "public": 0,
        "private": 0,
    }
    input_dir = audit_input_dir()
    source_payloads: dict[str, bytes] = {}
    source_bundles: dict[str, dict] = {}
    for source, filename in SOURCE_FILES.items():
        expected = by_segment[source]
        if expected.get("filename") != filename:
            raise RuntimeError(f"Pinned filename mismatch for source segment {source!r}")
        source_path = input_dir / filename
        try:
            source_bytes = source_path.read_bytes()
            bundle = json.loads(source_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read authorized input {filename!r}") from exc
        repositories = bundle.get("repositories") if isinstance(bundle, dict) else None
        if not isinstance(repositories, list):
            raise RuntimeError(f"Authorized input {filename!r} has no repositories list")
        visibility_counts = {"public": 0, "private": 0}
        for index, row in enumerate(repositories):
            if not isinstance(row, dict):
                raise RuntimeError(f"{source} row {index} is not an object")
            visibility_counts[source_visibility(row, source=source, index=index)] += 1
            source_archived(row, source=source, index=index)
        actual = {
            "source_segment": source,
            "filename": filename,
            "rows": len(repositories),
            "public": visibility_counts["public"],
            "private": visibility_counts["private"],
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
        }
        if actual != expected:
            raise RuntimeError(
                f"Authorized input {filename!r} does not match its pinned bytes/counts",
            )
        source_payloads[source] = source_bytes
        source_bundles[source] = bundle
        live_totals["repositories"] += actual["rows"]
        live_totals["public"] += actual["public"]
        live_totals["private"] += actual["private"]

    if manifest.get("totals") != live_totals:
        raise RuntimeError("Pinned input manifest totals do not match the live inputs")
    return manifest, manifest_bytes, source_payloads, source_bundles


def markdown(source: str) -> nbformat.NotebookNode:
    rendered = dedent(source).strip()
    cell_id = hashlib.sha256(f"markdown\0{rendered}".encode()).hexdigest()[:8]
    return nbformat.v4.new_markdown_cell(rendered, id=cell_id)


def code(source: str) -> nbformat.NotebookNode:
    rendered = dedent(source).strip()
    cell_id = hashlib.sha256(f"code\0{rendered}".encode()).hexdigest()[:8]
    return nbformat.v4.new_code_cell(rendered, id=cell_id)


cells = [
    markdown(
        """
        # ORGANVM reader-mode documentation estate audit

        **Audit date:** 2026-08-31

        **Scope:** 323 repositories visible through the linked GitHub context

        **Decision:** preserve one canonical factual substrate and expose it through
        class-appropriate reader routes; repair truth and authority drift before
        expanding search surfaces.

        ## TL;DR

        This notebook normalizes seven independently produced repository inventories,
        validates their coverage and scoring, publishes aggregate estate statistics,
        and emits a privacy-safe public rollout queue. Private repository names and
        findings remain outside the committed artifacts.
        """,
    ),
    markdown(
        """
        ## Context & Methods

        Each repository was inspected read-only and classified A–F. Seven dimensions
        were scored from 0–4: orientation, technical depth, conceptual depth,
        commercial relevance, evidence, search surface, and cross-linking. The seven
        audit segments use slightly different field names, so this notebook maps them
        into one schema and then asserts:

        - exactly 323 rows and 323 unique `owner/repository` keys;
        - classes are limited to A–F;
        - visibility is public or private;
        - all seven dimension scores fall within 0–4;
        - recomputed totals agree with the normalized dimensions.

        The ranking is editorial, not a claim of mathematical optimality. It combines
        documentation class, public leverage, evidence/truth repair, and the explicit
        recommendations recorded by each audit segment. Wave 0 establishes authority;
        five pilots stress distinct rhetorical modes; the following twenty are the
        first conversion queue.

        ### Key assumptions

        - Repository visibility and metadata reflect the authorized exports captured
          for the 2026-08-31 audit, not a continuously refreshed GitHub view.
        - Each repository is the unit of analysis; all seven rubric dimensions carry
          equal weight and use the source auditors' integer scores.
        - A 0–28 total is descriptive, not a quality ranking. Conversion order also
          considers documentation class, truth/identity risk, public leverage, and
          segment recommendations.
        - The seven raw exports are transient, access-controlled inputs. They are
          intentionally absent from this public repository; the committed manifest
          records filenames, counts, and hashes, not row-level private data.
        """,
    ),
    markdown(
        """
        ## Data

        The input grain is one repository per row across seven non-overlapping audit
        segments. The next cells load the authorized exports, normalize their field
        aliases, and validate coverage, visibility, classification, score completeness,
        and source totals before any public artifact is written.
        """,
    ),
    code(
        """
        from __future__ import annotations

        import hashlib
        import json
        import os
        import re
        from pathlib import Path

        import pandas as pd
        from IPython.display import Markdown, display

        pd.set_option("display.max_colwidth", 100)

        DIMENSIONS = (
            "orientation",
            "technical_depth",
            "conceptual_depth",
            "commercial_relevance",
            "evidence",
            "seo_surface",
            "cross_linking",
        )
        SCORE_ALIASES = {
            "orientation": ("orientation",),
            "technical_depth": ("technical_depth", "technical"),
            "conceptual_depth": ("conceptual_depth", "conceptual"),
            "commercial_relevance": ("commercial_relevance", "commercial"),
            "evidence": ("evidence",),
            "seo_surface": ("seo_surface", "seo"),
            "cross_linking": ("cross_linking",),
        }
        SOURCE_FILES = {
            "personal": "personal.json",
            "ergon": "ergon.json",
            "theoria_poiesis": "theoria-poiesis.json",
            "governance_comms": "governance-comms.json",
            "umbrella_core": "umbrella-core.json",
            "umbrella_extended": "umbrella-extended.json",
            "organvm_gap": "organvm-gap.json",
        }

        INPUT_DIR = Path(
            os.environ.get("ORGANVM_DOC_AUDIT_INPUT_DIR", "../../../audit")
        ).resolve()
        OUTPUT_DIR = Path.cwd().resolve()
        manifest_path = OUTPUT_DIR / "reader-mode-input-manifest.json"
        pinned_input_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if pinned_input_manifest.get("schema_version") != "reader-mode-input-manifest.v1":
            raise ValueError("Pinned input manifest has an unsupported schema version")
        pinned_sources = pinned_input_manifest.get("sources")
        if not isinstance(pinned_sources, list):
            raise TypeError("Pinned input manifest sources must be a list")
        pinned_by_segment = {
            item["source_segment"]: item
            for item in pinned_sources
            if isinstance(item, dict) and isinstance(item.get("source_segment"), str)
        }
        if len(pinned_by_segment) != len(pinned_sources):
            raise ValueError("Pinned input manifest has invalid or duplicate source segments")
        if set(pinned_by_segment) != set(SOURCE_FILES):
            raise ValueError("Pinned input manifest source segments do not match the notebook")


        def manifest_visibility(row, source, index):
            visibility = row.get("visibility")
            if visibility in {"public", "private"}:
                return visibility
            if visibility is not None:
                raise ValueError(
                    f"{source} row {index} has invalid visibility: {visibility!r}"
                )
            public = row.get("metadata", {}).get("public")
            if isinstance(public, bool):
                return "public" if public else "private"
            raise ValueError(f"{source} row {index} has no valid visibility")


        raw = {}
        live_input_sources = []
        for source, filename in SOURCE_FILES.items():
            expected = pinned_by_segment[source]
            if expected.get("filename") != filename:
                raise ValueError(f"Pinned filename mismatch for source segment {source}")
            source_path = INPUT_DIR / filename
            source_bytes = source_path.read_bytes()
            bundle = json.loads(source_bytes)
            repositories = bundle.get("repositories") if isinstance(bundle, dict) else None
            if not isinstance(repositories, list):
                raise TypeError(f"Authorized input {filename} has no repositories list")
            visibility_counts = {"public": 0, "private": 0}
            for index, row in enumerate(repositories):
                if not isinstance(row, dict):
                    raise TypeError(f"{source} row {index} is not an object")
                visibility_counts[manifest_visibility(row, source, index)] += 1
            actual = {
                "source_segment": source,
                "filename": filename,
                "rows": len(repositories),
                "public": visibility_counts["public"],
                "private": visibility_counts["private"],
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
            if actual != expected:
                raise ValueError(
                    f"Authorized input {filename} does not match its pinned bytes/counts"
                )
            raw[source] = bundle
            live_input_sources.append(actual)

        live_input_totals = {
            "source_segments": len(live_input_sources),
            "repositories": sum(item["rows"] for item in live_input_sources),
            "public": sum(item["public"] for item in live_input_sources),
            "private": sum(item["private"] for item in live_input_sources),
        }
        if pinned_input_manifest.get("totals") != live_input_totals:
            raise ValueError("Pinned input manifest totals do not match the live inputs")
        source_counts = {
            source: len(bundle["repositories"])
            for source, bundle in raw.items()
        }
        source_count_display = {
            SOURCE_FILES[source]: count for source, count in source_counts.items()
        }
        display(
            pd.DataFrame.from_dict(
                source_count_display,
                orient="index",
                columns=["repository rows"],
            )
        )
        """,
    ),
    code(
        """
        def normalize_visibility(row):
            visibility = row.get("visibility")
            if visibility in {"public", "private"}:
                return visibility
            if visibility is not None:
                raise ValueError(
                    f"Invalid visibility for {row.get('repository')}: {visibility!r}"
                )
            public = row.get("metadata", {}).get("public")
            if isinstance(public, bool):
                return "public" if public else "private"
            raise ValueError(f"Cannot resolve visibility for {row.get('repository')}")


        def normalize_repository(source, bundle, row):
            if SOURCE_FILES[source] == "personal.json":
                return f"{bundle.get('owner', '4444J99')}/{row['name']}"
            return row["repository"]


        def require_integer(value, field, repository):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    f"{repository}: {field} must be an integer, got {type(value).__name__}"
                )
            return value


        def normalize_scores(row, repository):
            source_scores = row.get("scores", {})
            result = {}
            for dimension, aliases in SCORE_ALIASES.items():
                present = [key for key in aliases if source_scores.get(key) is not None]
                if len(present) != 1:
                    raise ValueError(
                        f"{repository}: expected exactly one score alias for {dimension}; "
                        f"found {present}"
                    )
                source_key = present[0]
                result[dimension] = require_integer(
                    source_scores[source_key], f"scores.{source_key}", repository
                )

            total_candidates = [
                ("scores.total", source_scores.get("total")),
                ("score_total", row.get("score_total")),
                ("total", row.get("total")),
            ]
            present_totals = [
                (field, require_integer(value, field, repository))
                for field, value in total_candidates
                if value is not None
            ]
            if not present_totals:
                raise ValueError(f"{repository}: source total is required for this audit")
            if len({value for _, value in present_totals}) != 1:
                raise ValueError(
                    f"{repository}: conflicting source totals in "
                    f"{[field for field, _ in present_totals]}"
                )

            result["source_total"] = present_totals[0][1]
            result["total"] = sum(result[dimension] for dimension in DIMENSIONS)
            if result["source_total"] != result["total"]:
                raise ValueError(
                    f"{repository}: source total {result['source_total']} does not equal "
                    f"recomputed total {result['total']}"
                )
            return result


        def normalize_readme(source, row):
            if SOURCE_FILES[source] == "personal.json":
                return bool(row.get("readme", {}).get("present"))
            if SOURCE_FILES[source] == "ergon.json":
                return bool(row.get("readme_observation", {}).get("fetched"))
            if SOURCE_FILES[source] == "theoria-poiesis.json":
                return int(row.get("readme_words", 0)) > 0
            if SOURCE_FILES[source] == "umbrella-extended.json":
                return bool(row.get("readme", {}).get("present"))
            if SOURCE_FILES[source] == "organvm-gap.json":
                return bool(row.get("readme", {}).get("present"))
            return None


        def normalize_archived(row, source, index):
            metadata = row.get("metadata", {})
            if not isinstance(metadata, dict):
                raise TypeError(f"{source} row {index} has invalid metadata")
            value = row.get("archived", metadata.get("archived", False))
            if not isinstance(value, bool):
                raise TypeError(
                    f"{source} row {index} has invalid archived value: {value!r}"
                )
            return value


        def normalize_row(source, bundle, row, index):
            repository = normalize_repository(source, bundle, row)
            scores = normalize_scores(row, repository)
            metadata = row.get("metadata", {})
            finding = (
                row.get("finding")
                or row.get("note")
                or row.get("observed")
                or row.get("evidence_bounded_note")
                or "; ".join(row.get("truth_or_identity_findings", []))
                or ""
            )
            role = (
                row.get("repository_role")
                or row.get("surface_role")
                or row.get("role")
                or row.get("surface", {}).get("role")
                or "unspecified"
            )
            priority = (
                row.get("conversion_priority")
                or row.get("conversion_wave")
                or row.get("priority")
                or "unranked"
            )
            archived = normalize_archived(row, source, index)
            return {
                "repository": repository,
                "source_segment": source,
                "visibility": normalize_visibility(row),
                "documentation_class": row.get("documentation_class") or row.get("class"),
                "repository_role": role,
                "priority": priority,
                "archived": archived,
                "has_readme": normalize_readme(source, row),
                **scores,
                "finding": finding,
                "recommended_treatment": row.get("recommended_treatment", ""),
                "recommended_reader_modes": row.get("recommended_reader_modes", []),
                "industry_clusters": row.get("industry_clusters", []),
                "concept_clusters": row.get("concept_clusters", []),
                "topics": metadata.get("topics", []),
                "url": row.get("url") or f"https://github.com/{repository}",
            }


        def require(condition, message):
            if not condition:
                raise ValueError(message)


        rows = [
            normalize_row(source, bundle, row, index)
            for source, bundle in raw.items()
            for index, row in enumerate(bundle["repositories"])
        ]
        inventory = pd.DataFrame(rows).sort_values("repository").reset_index(drop=True)

        require(len(inventory) == 323, f"expected 323 rows, found {len(inventory)}")
        require(
            inventory["repository"].str.casefold().nunique() == 323,
            "repository keys are not unique case-insensitively",
        )
        require(
            len(SOURCE_FILES) == 7,
            f"expected seven source segments, found {len(SOURCE_FILES)}",
        )
        require(inventory["source_segment"].nunique() == 7, "source segment coverage drifted")
        require(
            set(inventory["documentation_class"]) <= set("ABCDEF"),
            "documentation classes must be limited to A-F",
        )
        require(
            set(inventory["visibility"]) <= {"public", "private"},
            "visibility values must be public or private",
        )
        for dimension in DIMENSIONS:
            require(
                inventory[dimension].between(0, 4).all(),
                f"{dimension} contains an out-of-range score",
            )
        require(
            (inventory[list(DIMENSIONS)].sum(axis=1) == inventory["total"]).all(),
            "normalized totals do not equal the seven dimensions",
        )
        require(
            (inventory["source_total"] == inventory["total"]).all(),
            "source totals do not equal recomputed totals",
        )
        visibility_validation = inventory["visibility"].value_counts().to_dict()
        require(
            visibility_validation == {"public": 239, "private": 84},
            f"visibility counts drifted: {visibility_validation}",
        )

        input_sources = []
        for source, filename in SOURCE_FILES.items():
            source_rows = inventory[inventory["source_segment"] == source]
            source_visibility = source_rows["visibility"].value_counts().to_dict()
            source_path = INPUT_DIR / filename
            input_sources.append(
                {
                    "source_segment": source,
                    "filename": filename,
                    "rows": int(len(source_rows)),
                    "public": int(source_visibility.get("public", 0)),
                    "private": int(source_visibility.get("private", 0)),
                    "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                }
            )
        require(
            sum(item["rows"] for item in input_sources) == 323,
            "normalized source row count drifted",
        )
        require(
            sum(item["public"] for item in input_sources) == 239,
            "normalized public row count drifted",
        )
        require(
            sum(item["private"] for item in input_sources) == 84,
            "normalized private row count drifted",
        )
        require(
            input_sources == live_input_sources,
            "normalized source counts or bytes drifted after manifest verification",
        )

        print(
            f"Validated {len(inventory)} unique repositories across "
            f"{len(SOURCE_FILES)} audit segments; every source total reconciles."
        )
        """,
    ),
    markdown("## Results"),
    code(
        """
        visibility_counts = inventory["visibility"].value_counts().to_dict()
        class_visibility = pd.crosstab(
            inventory["documentation_class"], inventory["visibility"], margins=True
        ).reindex(list("ABCDEF") + ["All"], fill_value=0)
        dimension_summary = (
            inventory.groupby("visibility")[list(DIMENSIONS)]
            .mean()
            .round(2)
            .T
        )

        display(Markdown(
            f"**Coverage:** {len(inventory)} repositories — "
            f"{visibility_counts.get('public', 0)} public and "
            f"{visibility_counts.get('private', 0)} private."
        ))
        display(class_visibility)
        display(Markdown("### Mean score by visibility (0–4)"))
        display(dimension_summary)
        """,
    ),
    code(
        """
        integrity_terms = (
            "unsupported", "stale", "broken", "mismatch", "contradict",
            "false", "drift", "zero-byte", "ambiguous", "truth repair",
        )
        inventory["integrity_attention"] = inventory["finding"].str.lower().map(
            lambda text: any(term in text for term in integrity_terms)
        )
        public_inventory = inventory[inventory["visibility"] == "public"].copy()

        private_full_identifiers = set(
            inventory.loc[inventory["visibility"] == "private", "repository"]
        )
        public_full_identifiers = set(
            inventory.loc[inventory["visibility"] == "public", "repository"]
        )
        from organvm_engine.documentation.privacy import (
            private_only_repository_slugs,
            redact_private_references,
            repository_reference_pattern,
        )

        private_only_slugs = private_only_repository_slugs(
            private_full_identifiers,
            public_full_identifiers,
        )
        private_reference_pattern = repository_reference_pattern(
            private_full_identifiers,
            private_only_slugs,
            public_full_identifiers,
        )

        for column in public_inventory.columns:
            public_inventory[column] = public_inventory[column].map(
                lambda value: redact_private_references(
                    value,
                    private_reference_pattern,
                )
            )
        public_integrity_count = int(public_inventory["integrity_attention"].sum())

        status_rows = pd.DataFrame(
            [
                {"finding": "Public repositories needing explicit truth/identity attention", "count": public_integrity_count},
                {"finding": "Public archived surfaces", "count": int((public_inventory["archived"] == True).sum())},
                {"finding": "Known public READMEs absent in segments that recorded presence", "count": int(((public_inventory["has_readme"] == False)).sum())},
                {"finding": "Public Class A/B/E projects", "count": int(public_inventory["documentation_class"].isin(["A", "B", "E"]).sum())},
            ]
        )
        display(status_rows)
        """,
    ),
    markdown(
        """
        ## Authority architecture

        The audit rejects a new standalone documentation-engine repository. Existing
        authorities already divide the work cleanly:

        | Authority | Repository | Owns |
        |---|---|---|
        | Editorial contract | `organvm/editorial-standards` | README v2, audience templates, rubric, language |
        | Data contract | `organvm-iv-taxis/schema-definitions` | `project-record.v1` and assertion/evidence schemas |
        | Runtime | `organvm/organvm-engine` | audit and validation commands, machine-readable receipts |
        | Fleet policy | `organvm/.github` | organization-wide adoption requirements and repository hygiene |
        | Reusable enforcement | `organvm-iv-taxis/system-governance-framework` | reusable CI invoking the runtime |
        | Fleet rollout | `organvm-iv-taxis/orchestration-start-here` | conversion waves, execution tracking, compliance reporting |

        Public renderers remain downstream consumers: portfolio, showcase, and
        stakeholder portal express the same facts for different readers.
        """,
    ),
    markdown("## Conversion program"),
    code(
        """
        pilots = [
            (1, "4444J99/limen", "claims-ledger and infrastructure/governance pilot"),
            (2, "organvm/the-thing-without-a-name", "creative, scholarly, production, and provenance pilot"),
            (3, "4444J99/peer-audited--behavioral-blockchain", "technical, commercial, ethical, and live-status pilot"),
            (4, "4444J99/your-fit-tailored", "specification-first theory/product pilot"),
            (5, "4444J99/hokage-chess", "prototype-vs-product pilot after mandatory truth repair"),
        ]

        next_twenty = [
            (1, "organvm-iii-ergon/public-record-data-scrapper", "strong public product/evidence front door"),
            (2, "organvm-iii-ergon/life-my--midst--in", "employment, identity theory, architecture, and evaluation"),
            (3, "organvm-iii-ergon/the-actual-news", "public purpose plus protocol/conformance evidence"),
            (4, "organvm-iii-ergon/classroom-rpg-aetheria", "pedagogy, product, system, and evaluator routes"),
            (5, "organvm-iii-ergon/parlor-games--ephemera-engine", "runnable creative system with honest design status"),
            (6, "organvm-ii-poiesis/ivi374ivi027-05", "bounded multimedia/literary work and preservation record"),
            (7, "organvm/a-organvm", "canonical flagship with no audience routing"),
            (8, "organvm/organvm-engine", "largest implementation-to-documentation mismatch"),
            (9, "organvm/radix-recursiva-solve-coagula-redi", "flagship theory/runtime synthesis"),
            (10, "organvm/recursive-engine--generative-entity", "mature theory/runtime flagship"),
            (11, "organvm/linguistic-atomization-framework", "balanced technical-humanities record"),
            (12, "organvm/alchemical-synthesizer", "creative technology flagship"),
            (13, "organvm/metasystem-master", "repair zero-byte and evidence drift before conversion"),
            (14, "organvm/adaptive-personal-syllabus", "repair tracked artifacts and provenance before conversion"),
            (15, "organvm-iv-taxis/system-governance-framework", "document the reusable enforcement surface"),
            (16, "organvm-iv-taxis/distribution-strategy", "source audience and search-intent mappings"),
            (17, "organvm-vii-kerygma/portfolio", "general, hiring, and client renderer"),
            (18, "organvm-vii-kerygma/showcase-portfolio", "humanities, curatorial, and grant renderer"),
            (19, "organvm-vii-kerygma/stakeholder-portal", "evaluator and operational evidence renderer"),
            (20, "organvm/4444J99", "problem-domain top-of-funnel above the internal ontology"),
        ]

        require(
            [rank for rank, _, _ in pilots] == list(range(1, 6)),
            "pilot ranks must be contiguous from 1 through 5",
        )
        require(
            [rank for rank, _, _ in next_twenty] == list(range(1, 21)),
            "next-twenty ranks must be contiguous from 1 through 20",
        )
        curated_sequence = [repo for _, repo, _ in pilots + next_twenty]
        require(
            len(curated_sequence) == len(set(curated_sequence)),
            "curated queues overlap",
        )
        curated_names = set(curated_sequence)
        public_names = set(public_inventory["repository"])
        missing_curated = sorted(curated_names - public_names)
        require(
            not missing_curated,
            f"curated public repositories absent from inventory: {missing_curated}",
        )

        public_by_repository = public_inventory.set_index("repository")
        require(
            public_by_repository.index.is_unique,
            "public repository index is not unique",
        )


        def selection_records(entries):
            selected = []
            for rank, repository, reason in entries:
                source_row = public_by_repository.loc[repository]
                require(
                    source_row["finding"] or source_row["priority"] != "unranked",
                    f"{repository}: curated entry lacks a finding or priority",
                )
                selected.append(
                    {
                        "rank": rank,
                        "repository": repository,
                        "class": source_row["documentation_class"],
                        "audit_score": int(source_row["total"]),
                        "source_priority": source_row["priority"],
                        "integrity_gate": bool(source_row["integrity_attention"]),
                        "reason": reason,
                    }
                )
            return selected


        pilot_records = selection_records(pilots)
        queue_records = selection_records(next_twenty)
        pilot_table = pd.DataFrame(pilot_records)
        queue_table = pd.DataFrame(queue_records)
        display(Markdown("### Five pilots"))
        display(pilot_table)
        display(Markdown("### Next twenty conversions"))
        display(queue_table)
        """,
    ),
    markdown(
        """
        ## Truth and authority gates

        Conversion is blocked when it would amplify a false current state, broken
        canonical identity, unsupported metric, ambiguous license, or placeholder
        surface. The initial gate set includes:

        - repair Hokage Chess's Python/CLI claims against its bounded TypeScript helper prototype;
        - route the 38-commit-behind account-level copy of The Thing to the canonical
          `organvm/the-thing-without-a-name` record instead of forking full editions;
        - replace stale Styx test totals with exact-commit receipts and repair its link;
        - label Your Fit as specification-first until runtime evidence exists;
        - resolve Limen's missing license before calling it open source;
        - reconcile organization profiles and transferred-repository identities;
        - repair or redirect `organvm/docs`, `organvm/metasystem-master`, and retired Pages copies;
        - align editorial, schema, and engine owner URLs with their live authorities.

        These are evidence repairs, not copy edits. Search expansion follows the repair.
        """,
    ),
    markdown("## Publish privacy-safe artifacts"),
    code(
        """
        generated_at = pinned_input_manifest["generated_at"]
        input_manifest = pinned_input_manifest
        aggregate_summary = {
            "audit_date": "2026-08-31",
            "generated_at": generated_at,
            "scope": {
                "repositories": int(len(inventory)),
                "public": int(visibility_counts.get("public", 0)),
                "private": int(visibility_counts.get("private", 0)),
                "source_segments": source_counts,
                "source_manifest": "reader-mode-input-manifest.json",
                "linked_accounts": 11,
                "coverage_note": "The installation endpoint capped organvm at 100 rows; authenticated repository search added 70 omitted rows. The linked a-organvm account exposed zero repositories; organvm/a-organvm is a distinct repository.",
            },
            "documentation_classes": {
                visibility: {
                    cls: int(class_visibility.loc[cls].get(visibility, 0))
                    for cls in "ABCDEF"
                }
                for visibility in ("public", "private")
            },
            "documentation_class_totals": {
                cls: int(class_visibility.loc[cls].get("All", 0))
                for cls in "ABCDEF"
            },
            "mean_scores": {
                visibility: {
                    dimension: round(float(value), 3)
                    for dimension, value in group[list(DIMENSIONS)].mean().items()
                }
                for visibility, group in inventory.groupby("visibility")
            },
            "public_integrity_attention": public_integrity_count,
            "privacy": "Private repository names and row-level findings are excluded from committed artifacts.",
        }

        public_columns = [
            "repository", "visibility", "documentation_class", "repository_role",
            "priority", "archived", "has_readme", *DIMENSIONS, "source_total", "total",
            "integrity_attention", "finding", "recommended_treatment", "url",
            "recommended_reader_modes", "industry_clusters", "concept_clusters", "topics",
        ]
        public_records = json.loads(
            public_inventory[public_columns].to_json(orient="records")
        )
        rollout = {
            "audit_date": "2026-08-31",
            "generated_at": generated_at,
            "dimensions": list(DIMENSIONS),
            "authority_repositories": [
                "organvm/editorial-standards",
                "organvm-iv-taxis/schema-definitions",
                "organvm/organvm-engine",
                "organvm/.github",
                "organvm-iv-taxis/system-governance-framework",
                "organvm-iv-taxis/orchestration-start-here",
            ],
            "selection_method": (
                "Editorial order combining class, public leverage, source-segment "
                "recommendations, and truth/identity gates; audit_score is descriptive, "
                "not the sole ranking function."
            ),
            "pilots": pilot_records,
            "next_twenty": queue_records,
            "public_inventory": public_records,
        }

        class_rows = [
            f"| {cls} | {int(class_visibility.loc[cls].get('public', 0))} | "
            f"{int(class_visibility.loc[cls].get('private', 0))} |"
            for cls in "ABCDEF"
        ]
        pilot_rows = [
            f"| {item['rank']} | `{item['repository']}` | {item['class']} | "
            f"{item['audit_score']} | {item['source_priority']} | {item['reason']} |"
            for item in pilot_records
        ]
        queue_rows = [
            f"| {item['rank']} | `{item['repository']}` | {item['class']} | "
            f"{item['audit_score']} | {item['source_priority']} | {item['reason']} |"
            for item in queue_records
        ]
        report_lines = [
            "# ORGANVM reader-mode documentation estate audit",
            "",
            "Audit date: 2026-08-31",
            "",
            "## Outcome",
            "",
            (
                f"All **{len(inventory)}** repositories visible through the linked "
                f"GitHub context were classified and scored: "
                f"**{visibility_counts.get('public', 0)} public** and "
                f"**{visibility_counts.get('private', 0)} private**. The implementation "
                "uses existing editorial, schema, runtime, governance, and orchestration "
                "authorities rather than adding a documentation-engine repository."
            ),
            "",
            (
                "The public contract is one canonical factual project record, "
                "evidence-linked material claims, class-specific reader routes, and "
                "truth repair before search expansion. Private repository identifiers "
                "and row-level findings remain outside this report."
            ),
            "",
            "## Data and validation",
            "",
            (
                "The audit uses seven authorized exports at one "
                "repository per row. All 323 source totals reconcile with the seven "
                "0–4 dimension scores; repository identifiers are unique; and class, "
                "visibility, and expected coverage checks pass."
            ),
            "",
            (
                "The public input manifest records source filenames, row and visibility "
                "counts, and SHA-256 hashes. Raw exports are not committed, so rerunning "
                "is possible only with separately retained authorized copies."
            ),
            "",
            "## Documentation classes",
            "",
            "| Class | Public | Private |",
            "|---|---:|---:|",
            *class_rows,
            "",
            "## Authority map",
            "",
            "| Responsibility | Canonical repository |",
            "|---|---|",
            "| Editorial contract, rubric, and templates | `organvm/editorial-standards` |",
            "| Project and assertion schemas | `organvm-iv-taxis/schema-definitions` |",
            "| Audit and validation runtime | `organvm/organvm-engine` |",
            "| Fleet adoption policy | `organvm/.github` |",
            "| Reusable CI invocation | `organvm-iv-taxis/system-governance-framework` |",
            "| Rollout waves and execution receipts | `organvm-iv-taxis/orchestration-start-here` |",
            "",
            "## Five pilots",
            "",
            (
                "Ranks combine public leverage, rhetorical coverage, source recommendations, "
                "and truth gates. The audit score is shown for traceability, not used as a "
                "standalone ordering function."
            ),
            "",
            "| Rank | Repository | Class | Score / 28 | Source priority | Why this pilot |",
            "|---:|---|:---:|---:|---|---|",
            *pilot_rows,
            "",
            "## Next twenty conversions",
            "",
            "| Rank | Repository | Class | Score / 28 | Source priority | Value / gap / leverage |",
            "|---:|---|:---:|---:|---|---|",
            *queue_rows,
            "",
            "## Gates before expansion",
            "",
            "- Correct false or stale implementation, deployment, test, owner, license, and provenance claims.",
            "- Do not create audience editions for archives, forks, or deployment artifacts beyond their class minimum.",
            "- Treat industry mappings as proposed unless a claim record substantiates pilot or deployment status.",
            "- Keep private repository identifiers and evidence out of public generated inventories.",
            "- Preserve the endpoint coverage caveat recorded in the aggregate summary.",
            "",
            "## Reproduction boundary",
            "",
            (
                "Run `build_reader_mode_estate_audit.py` with "
                "`ORGANVM_DOC_AUDIT_INPUT_DIR` pointing to separately retained, "
                "authorized copies of the seven exports whose hashes appear in "
                "`reader-mode-input-manifest.json`. The public repository alone is "
                "not a self-contained copy of the raw audit data."
            ),
        ]
        report = "\\n".join(report_lines) + "\\n"

        serialized_artifacts = {
            "reader-mode-estate-summary.json": json.dumps(
                aggregate_summary, indent=2, allow_nan=False
            ) + "\\n",
            "reader-mode-public-rollout.json": json.dumps(
                rollout, indent=2, allow_nan=False
            ) + "\\n",
            "reader-mode-estate-audit.md": report,
        }
        manifest_scan_view = json.loads(json.dumps(input_manifest))
        for source in manifest_scan_view["sources"]:
            source["source_segment"] = "[source segment]"
        summary_scan_view = json.loads(json.dumps(aggregate_summary))
        summary_scan_view["scope"]["source_segments"] = list(
            summary_scan_view["scope"]["source_segments"].values()
        )
        privacy_scan_artifacts = {
            **serialized_artifacts,
            "reader-mode-input-manifest.json": json.dumps(manifest_scan_view),
            "reader-mode-estate-summary.json": json.dumps(summary_scan_view),
        }
        privacy_hits = {
            filename: sum(
                match.lastgroup != "public_full"
                for match in private_reference_pattern.finditer(payload)
            )
            for filename, payload in privacy_scan_artifacts.items()
        }
        require(
            not any(privacy_hits.values()),
            "private repository identifiers detected in public payloads: "
            f"{sum(privacy_hits.values())} hit(s)",
        )

        for filename, payload in serialized_artifacts.items():
            (OUTPUT_DIR / filename).write_text(payload, encoding="utf-8")

        print("Wrote reader-mode-estate-summary.json")
        print("Wrote reader-mode-public-rollout.json")
        print("Wrote reader-mode-estate-audit.md")
        """,
    ),
    markdown(
        """
        ## Takeaways

        1. Documentation density is not the estate's primary failure; shared entry
           order and authority drift are.
        2. Class A projects warrant five routes, while components, deployment
           artifacts, research works, and archives should retain smaller contracts.
        3. The first implementation wave must couple rhetoric with claim-level
           evidence, otherwise SEO multiplies contradictions.
        4. The five pilots intentionally cover infrastructure, creative practice,
           technical/commercial systems, specification-first work, and design-only
           truth repair.
        5. The public rollout can be generated without exposing private repository
           identities.
        """,
    ),
]

notebook = nbformat.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
)


def execute_in_process(document: nbformat.NotebookNode) -> nbformat.NotebookNode:
    """Execute cells without ZMQ for restricted environments.

    IPython's capture layer preserves stream and rich display outputs. This is a
    fallback for sandboxes that prohibit both TCP and IPC kernel sockets; normal
    environments continue to use nbclient.
    """
    from IPython.core.interactiveshell import InteractiveShell
    from IPython.utils.capture import capture_output

    shell = InteractiveShell.instance()
    shell.reset(new_session=True)
    execution_count = 0
    for cell in document.cells:
        if cell.cell_type != "code":
            continue
        execution_count += 1
        cell.execution_count = execution_count
        cell.outputs = []
        with capture_output(display=True) as captured:
            result = shell.run_cell(cell.source, store_history=False)
        if captured.stdout:
            cell.outputs.append(
                nbformat.v4.new_output("stream", name="stdout", text=captured.stdout),
            )
        if captured.stderr:
            cell.outputs.append(
                nbformat.v4.new_output("stream", name="stderr", text=captured.stderr),
            )
        for output in captured.outputs:
            cell.outputs.append(
                nbformat.v4.new_output(
                    "display_data",
                    data=output.data,
                    metadata=output.metadata,
                ),
            )
        error = result.error_before_exec or result.error_in_exec
        if error is not None:
            cell.outputs.append(
                nbformat.v4.new_output(
                    "error",
                    ename=type(error).__name__,
                    evalue=str(error),
                    traceback=traceback.format_exception(type(error), error, error.__traceback__),
                ),
            )
            raise RuntimeError(f"Notebook cell {execution_count} failed") from error
    document.metadata["execution"] = {
        "mode": "in-process-ipython",
        "reason": "Kernel sockets unavailable or explicitly disabled",
    }
    return document


def execute_notebook(
    document: nbformat.NotebookNode,
    *,
    input_dir: Path,
    output_dir: Path,
) -> nbformat.NotebookNode:
    """Execute only against private verified snapshots in an isolated staging cwd."""
    previous_cwd = Path.cwd()
    previous_input_dir = os.environ.get("ORGANVM_DOC_AUDIT_INPUT_DIR")
    try:
        os.environ["ORGANVM_DOC_AUDIT_INPUT_DIR"] = str(input_dir)
        os.chdir(output_dir)
        if os.environ.get("ORGANVM_NOTEBOOK_EXECUTION") == "in-process":
            executed = execute_in_process(document)
        else:
            try:
                client = NotebookClient(
                    document,
                    timeout=600,
                    kernel_name="python3",
                    allow_errors=False,
                )
                executed = client.execute()
                executed.metadata["execution"] = {"mode": "nbclient"}
            except RuntimeError as exc:
                if "Kernel died" not in str(exc):
                    raise
                executed = execute_in_process(document)
    finally:
        os.chdir(previous_cwd)
        if previous_input_dir is None:
            os.environ.pop("ORGANVM_DOC_AUDIT_INPUT_DIR", None)
        else:
            os.environ["ORGANVM_DOC_AUDIT_INPUT_DIR"] = previous_input_dir
    return executed


def repository_identifiers_by_visibility(
    verified_source_bundles: dict[str, dict],
) -> tuple[set[str], set[str]]:
    """Resolve identifiers only from manifest-verified parsed source snapshots."""
    private_identifiers: set[str] = set()
    public_identifiers: set[str] = set()
    for source, filename in SOURCE_FILES.items():
        bundle = verified_source_bundles[source]
        for index, row in enumerate(bundle["repositories"]):
            visibility = source_visibility(row, source=source, index=index)
            if filename == "personal.json":
                repository = f"{bundle.get('owner', '4444J99')}/{row['name']}"
            else:
                repository = row["repository"]
            if visibility == "private":
                private_identifiers.add(repository)
            else:
                public_identifiers.add(repository)
    return private_identifiers, public_identifiers


def materialize_verified_inputs(
    input_dir: Path,
    source_payloads: dict[str, bytes],
) -> None:
    """Write the exact verified snapshots into an owner-private execution directory."""
    input_dir.mkdir(mode=0o700)
    for source, filename in SOURCE_FILES.items():
        target = input_dir / filename
        with target.open("xb") as stream:
            stream.write(source_payloads[source])
        target.chmod(0o600)


def bare_slug_scan_payload(path: Path, payload: str) -> str:
    """Return privacy-bearing content while excluding structural source labels."""
    if path.suffix == ".py":
        declaration = re.compile(
            r"(?m)^[ \t]*(?P<name>SOURCE_FILES|PUBLIC_PROSE_REWRITES|"
            r"PUBLIC_EXACT_REWRITES|public_prose_rewrites|public_exact_rewrites)"
            r"[ \t]*=[ \t]*(?P<opening>[{([])",
        )
        spans: list[tuple[int, int]] = []

        def offset_for(fragment: str, row: int, column: int) -> int:
            line_offsets = [0]
            line_offsets.extend(
                match.end() for match in re.finditer("\n", fragment)
            )
            return line_offsets[row - 1] + column

        for match in declaration.finditer(payload):
            declaration_tail = payload[match.start("opening") :]
            bracket_stack: list[str] = []
            declaration_end: int | None = None
            tokens = tokenize.generate_tokens(io.StringIO(declaration_tail).readline)
            try:
                for token in tokens:
                    if token.type != tokenize.OP:
                        continue
                    if token.string in "({[":
                        bracket_stack.append(token.string)
                    elif token.string in ")}]":
                        if not bracket_stack:
                            break
                        bracket_stack.pop()
                        if not bracket_stack:
                            declaration_end = offset_for(
                                declaration_tail,
                                token.end[0],
                                token.end[1],
                            )
                            break
            except tokenize.TokenError:
                pass
            if declaration_end is None:
                raise RuntimeError("Unterminated privacy-control declaration")
            fragment = declaration_tail[:declaration_end]
            try:
                expression = ast.parse(fragment, mode="eval").body
            except SyntaxError as exc:
                raise RuntimeError("Malformed privacy-control declaration") from exc
            structural_nodes: list[ast.Constant] = []
            declaration_name = match.group("name")
            if declaration_name == "SOURCE_FILES" and isinstance(expression, ast.Dict):
                for key, value in zip(expression.keys, expression.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and SOURCE_FILES.get(key.value) == value.value
                    ):
                        structural_nodes.extend((key, value))
            elif declaration_name in {
                "PUBLIC_PROSE_REWRITES",
                "public_prose_rewrites",
            } and isinstance(expression, (ast.List, ast.Tuple)):
                expected_pairs = set(PUBLIC_PROSE_REWRITES)
                for element in expression.elts:
                    if not isinstance(element, (ast.List, ast.Tuple)):
                        continue
                    if len(element.elts) != 2 or not all(
                        isinstance(item, ast.Constant) and isinstance(item.value, str)
                        for item in element.elts
                    ):
                        continue
                    pair = tuple(item.value for item in element.elts)
                    if pair in expected_pairs:
                        structural_nodes.extend(element.elts)
            elif declaration_name in {
                "PUBLIC_EXACT_REWRITES",
                "public_exact_rewrites",
            } and isinstance(expression, ast.Dict):
                for key, value in zip(expression.keys, expression.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and PUBLIC_EXACT_REWRITES.get(key.value) == value.value
                    ):
                        structural_nodes.extend((key, value))
            for node in structural_nodes:
                if node.end_lineno is None or node.end_col_offset is None:
                    raise RuntimeError("Privacy-control string lacks a source span")
                spans.append(
                    (
                        match.start("opening")
                        + offset_for(fragment, node.lineno, node.col_offset),
                        match.start("opening")
                        + offset_for(fragment, node.end_lineno, node.end_col_offset),
                    ),
                )
        for start, end in reversed(sorted(set(spans))):
            payload = payload[:start] + " " * (end - start) + payload[end:]
        return payload
    if path.suffix == ".ipynb":
        document = nbformat.reads(payload, as_version=4)
        cells_and_outputs: list[str] = []
        for cell in document.cells:
            if cell.cell_type == "markdown":
                cells_and_outputs.append(cell.source)
            elif cell.cell_type == "code":
                cells_and_outputs.append(
                    bare_slug_scan_payload(Path("notebook-cell.py"), cell.source),
                )
            cells_and_outputs.extend(json.dumps(output) for output in cell.get("outputs", []))
        return "\n".join(cells_and_outputs)
    if path.name == INPUT_MANIFEST.name:
        manifest = json.loads(payload)
        for source in manifest["sources"]:
            source["source_segment"] = "[source segment]"
        return json.dumps(manifest)
    if path.name == "reader-mode-estate-summary.json":
        summary = json.loads(payload)
        summary["scope"]["source_segments"] = list(
            summary["scope"]["source_segments"].values(),
        )
        return json.dumps(summary)
    return payload


def _read_regular_bytes_once(path: Path) -> bytes:
    """Read one bounded regular file through a no-follow descriptor."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"Cannot open staged artifact {path.name!r}") from exc
    try:
        identity_before = os.fstat(descriptor)
        if not stat.S_ISREG(identity_before.st_mode):
            raise RuntimeError(f"Staged artifact {path.name!r} is not a regular file")
        if identity_before.st_size > MAX_PUBLICATION_ARTIFACT_BYTES:
            raise RuntimeError(f"Staged artifact {path.name!r} exceeds the size limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PUBLICATION_ARTIFACT_BYTES:
                raise RuntimeError(f"Staged artifact {path.name!r} exceeds the size limit")
            chunks.append(chunk)
        identity_after = os.fstat(descriptor)
        if (
            identity_before.st_dev,
            identity_before.st_ino,
            identity_before.st_size,
            identity_before.st_mtime_ns,
        ) != (
            identity_after.st_dev,
            identity_after.st_ino,
            identity_after.st_size,
            identity_after.st_mtime_ns,
        ):
            raise RuntimeError(f"Staged artifact {path.name!r} changed while reading")
        payload = b"".join(chunks)
        if len(payload) != identity_before.st_size:
            raise RuntimeError(f"Staged artifact {path.name!r} changed while reading")
        return payload
    finally:
        os.close(descriptor)


def read_staged_candidate_bytes(stage_dir: Path) -> dict[Path, bytes]:
    """Read each staged publication candidate exactly once."""
    return {
        HERE / name: _read_regular_bytes_once(stage_dir / name)
        for name in PUBLISHED_ARTIFACT_NAMES
    }


def privacy_gate_candidate_bytes(
    candidate_bytes: dict[Path, bytes],
    *,
    manifest_bytes: bytes,
    private_reference_pattern: re.Pattern[str],
) -> int:
    """Scan the exact candidate bytes that will be published plus current peers."""
    candidate_text: dict[Path, str] = {}
    for path, payload in candidate_bytes.items():
        try:
            candidate_text[path] = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"Staged artifact {path.name!r} is not UTF-8") from exc
    try:
        manifest_text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Pinned input manifest is not UTF-8") from exc

    publication_paths = {
        path
        for path in HERE.iterdir()
        if path.is_file() and path.suffix in {".ipynb", ".json", ".md", ".py"}
    }
    publication_paths.update(candidate_text)
    publication_paths.add(INPUT_MANIFEST)
    privacy_hits_by_file: dict[str, int] = {}
    for path in sorted(publication_paths):
        if path in candidate_text:
            payload = candidate_text[path]
        elif path == INPUT_MANIFEST:
            payload = manifest_text
        else:
            try:
                payload = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Cannot scan public artifact {path.name!r}") from exc
        private_full_hits = sum(
            match.lastgroup == "private_full"
            for match in private_reference_pattern.finditer(payload)
        )
        private_reference_hits = sum(
            match.lastgroup != "public_full"
            for match in private_reference_pattern.finditer(
                bare_slug_scan_payload(path, payload),
            )
        )
        if hit_count := private_full_hits + private_reference_hits:
            privacy_hits_by_file[path.name] = hit_count
    if privacy_hits_by_file:
        rendered_hits = ", ".join(
            f"{name}={count}" for name, count in sorted(privacy_hits_by_file.items())
        )
        raise RuntimeError(
            "Detected private repository identifier hits in public artifacts: "
            + rendered_hits,
        )
    return len(publication_paths)


def _artifact_binding(path: Path) -> dict[str, int | str]:
    before = path.stat(follow_symlinks=False)
    payload = _read_regular_bytes_once(path)
    after = path.stat(follow_symlinks=False)
    if not _same_artifact_identity(before, after):
        raise RuntimeError(f"Artifact {path.name!r} changed while binding recovery")
    return {
        "device": before.st_dev, "inode": before.st_ino,
        "bytes": before.st_size, "mtime_ns": before.st_mtime_ns,
        "mode": stat.S_IMODE(before.st_mode),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _artifact_matches(path: Path, binding: dict | None) -> bool:
    if binding is None:
        return not path.exists() and not path.is_symlink()
    try:
        return _artifact_binding(path) == binding
    except (OSError, RuntimeError):
        return False


def _fsync_artifact_directory() -> None:
    descriptor = os.open(HERE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _artifact_publication_lock():
    import fcntl

    descriptor = os.open(
        HERE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _write_artifact_recovery(record: dict) -> None:
    """Durably replace complete metadata, never truncate the active recovery WAL."""
    payload = (json.dumps(record, sort_keys=True) + "\n").encode()
    if len(payload) > MAX_ARTIFACT_RECOVERY_BYTES:
        raise RuntimeError("Audit artifact recovery metadata exceeds its size limit")
    descriptor, name = tempfile.mkstemp(dir=HERE, prefix=".reader-mode-recovery.", suffix=".pending")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(HERE / ARTIFACT_RECOVERY_NAME)
        _fsync_artifact_directory()
    finally:
        temporary.unlink(missing_ok=True)


def _read_artifact_recovery() -> dict | None:
    path = HERE / ARTIFACT_RECOVERY_NAME
    try:
        status = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600
        or status.st_nlink != 1 or status.st_size > MAX_ARTIFACT_RECOVERY_BYTES
        or status.st_uid != os.geteuid()
    ):
        raise RuntimeError("Unsafe audit artifact recovery metadata")
    try:
        payload = _read_regular_bytes_once(path)
        rebound = path.stat(follow_symlinks=False)
        if any(getattr(status, field) != getattr(rebound, field) for field in (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size",
            "st_mtime_ns", "st_ctime_ns",
        )):
            raise RuntimeError("Audit artifact recovery metadata changed while reading")
        record = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("Malformed audit artifact recovery metadata") from exc
    root = HERE.stat()
    if (
        not isinstance(record, dict) or record.get("version") != 1
        or record.get("state") not in {"pending", "committed"}
        or record.get("root") != {"device": root.st_dev, "inode": root.st_ino}
        or not isinstance(record.get("transaction"), str)
        or not re.fullmatch(r"[0-9a-f]{48}", record["transaction"])
        or not isinstance(record.get("artifacts"), list)
        or not 1 <= len(record["artifacts"]) <= 64
    ):
        raise RuntimeError("Invalid audit artifact recovery metadata")
    targets: set[str] = set()
    for entry in record["artifacts"]:
        if not isinstance(entry, dict) or set(entry) != {
            "target", "temporary", "rollback", "displaced", "failed",
            "original_binding", "candidate_binding", "rollback_binding",
        }:
            raise RuntimeError("Invalid audit artifact recovery entry")
        target = entry.get("target")
        if (
            not isinstance(target, str) or not target or target.startswith(".")
            or Path(target).name != target or "/" in target or "\\" in target
            or target in targets
        ):
            raise RuntimeError("Unsafe audit artifact recovery target")
        targets.add(target)
        for field, suffix in (
            ("temporary", ".tmp"), ("rollback", ".rollback"),
            ("displaced", ".displaced"), ("failed", ".failed"),
        ):
            value = entry.get(field)
            if value is None and field == "rollback" and entry.get("original_binding") is None:
                continue
            if (
                not isinstance(value, str) or Path(value).name != value
                or not value.startswith(f".{target}.") or not value.endswith(suffix)
                or "/" in value or "\\" in value
            ):
                raise RuntimeError("Unsafe audit artifact recovery transaction path")
        for field in ("original_binding", "candidate_binding", "rollback_binding"):
            binding = entry.get(field)
            if binding is None and field != "candidate_binding":
                continue
            if (
                not isinstance(binding, dict)
                or set(binding) != {"device", "inode", "bytes", "mtime_ns", "mode", "sha256"}
                or any(type(binding[key]) is not int or binding[key] < 0 for key in (
                    "device", "inode", "bytes", "mtime_ns", "mode",
                ))
                or not isinstance(binding["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])
            ):
                raise RuntimeError("Invalid audit artifact recovery byte binding")
        if (entry["original_binding"] is None) != (entry["rollback_binding"] is None):
            raise RuntimeError("Incomplete audit artifact recovery preimage")
    return record


def _cleanup_artifact_recovery(record: dict) -> None:
    """Retire only exact recorded private aliases after the public state is durable."""
    _assert_artifact_recovery_root(record)
    for entry in record["artifacts"]:
        for field, binding_field in (
            ("temporary", "candidate_binding"), ("rollback", "rollback_binding"),
            ("displaced", "original_binding"), ("failed", "candidate_binding"),
        ):
            name = entry[field]
            if name is None:
                continue
            path = HERE / name
            if not path.exists() and not path.is_symlink():
                continue
            if not _artifact_matches(path, entry[binding_field]):
                raise RuntimeError(f"Audit recovery alias changed; retained {name}")
            _assert_artifact_recovery_root(record)
            path.unlink()
    _fsync_artifact_directory()
    _assert_artifact_recovery_root(record)
    (HERE / ARTIFACT_RECOVERY_NAME).unlink()
    _fsync_artifact_directory()


def _assert_artifact_recovery_root(record: dict) -> None:
    status = HERE.lstat()
    if not stat.S_ISDIR(status.st_mode) or record["root"] != {
        "device": status.st_dev, "inode": status.st_ino,
    }:
        raise RuntimeError("Audit artifact recovery directory changed")


def _recover_artifact_publication_locked() -> None:
    record = _read_artifact_recovery()
    if record is None:
        return
    if record["state"] == "committed":
        # A completed publication stays completed even if a user later edits it.
        _cleanup_artifact_recovery(record)
        return
    errors = []
    for entry in reversed(record["artifacts"]):
        _assert_artifact_recovery_root(record)
        target = HERE / entry["target"]
        original = entry["original_binding"]
        rollback = HERE / entry["rollback"] if entry["rollback"] is not None else None
        failed, displaced = HERE / entry["failed"], HERE / entry["displaced"]
        try:
            if _artifact_matches(target, original) or (
                rollback is not None and _artifact_matches(target, entry["rollback_binding"])
            ):
                continue
            if _artifact_matches(target, entry["candidate_binding"]):
                if failed.exists() or failed.is_symlink():
                    if not _artifact_matches(failed, entry["candidate_binding"]):
                        raise RuntimeError("rollback displacement changed")
                    _assert_artifact_recovery_root(record)
                    failed.unlink()
                    _fsync_artifact_directory()
                _assert_artifact_recovery_root(record)
                target.rename(failed)
                if not _artifact_matches(failed, entry["candidate_binding"]):
                    _restore_displaced_artifact(failed, target)
                    raise RuntimeError("candidate changed at recovery boundary")
                _fsync_artifact_directory()
            elif target.exists() or target.is_symlink():
                raise RuntimeError("concurrent public artifact preserved")
            if original is not None:
                if _artifact_matches(displaced, original):
                    source = displaced
                elif _artifact_matches(failed, entry["candidate_binding"]):
                    if rollback is None or not _artifact_matches(rollback, entry["rollback_binding"]):
                        raise RuntimeError("recorded rollback preimage is unavailable")
                    source = rollback
                else:
                    raise RuntimeError("recorded displacement is unavailable or changed")
                _assert_artifact_recovery_root(record)
                os.link(source, target, follow_symlinks=False)
            _fsync_artifact_directory()
        except (OSError, RuntimeError) as exc:
            errors.append(f"{target.name}: {exc}")
    if errors:
        raise RuntimeError("Audit artifact recovery incomplete; custody retained: " + "; ".join(errors))
    _fsync_artifact_directory()
    _cleanup_artifact_recovery(record)


def recover_artifact_publication() -> None:
    """Restore a pending public artifact set before consulting private inputs."""
    with _artifact_publication_lock():
        _recover_artifact_publication_locked()


def publish_exact_candidate_bytes(candidate_bytes: dict[Path, bytes]) -> None:
    with _artifact_publication_lock():
        _recover_artifact_publication_locked()
        if candidate_bytes:
            _publish_exact_candidate_bytes_locked(candidate_bytes)


def _publish_exact_candidate_bytes_locked(candidate_bytes: dict[Path, bytes]) -> None:
    """Publish one recoverable artifact set from already-scanned candidate bytes."""
    temporary_paths: dict[Path, Path] = {}
    rollback_paths: dict[Path, Path | None] = {}
    preimage_statuses: dict[Path, os.stat_result | None] = {}
    published: dict[Path, tuple[os.stat_result, bytes]] = {}
    recovery: dict | None = None
    recovery_entries: dict[Path, dict] = {}
    retain_rollback = False
    committing = False
    try:
        for target, payload in candidate_bytes.items():
            if target.parent != HERE or target.name.startswith("."):
                raise RuntimeError("Audit publication target must be a direct public artifact")
            descriptor, temporary_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            temporary_paths[target] = temporary
            try:
                os.fchmod(descriptor, 0o644)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                with suppress(OSError):
                    os.close(descriptor)
                raise
        for target in candidate_bytes:
            try:
                initial = target.stat(follow_symlinks=False)
            except FileNotFoundError:
                rollback_paths[target] = None
                preimage_statuses[target] = None
                continue
            if not stat.S_ISREG(initial.st_mode):
                raise RuntimeError(f"Published artifact {target.name!r} is not a regular file")
            preimage = _read_regular_bytes_once(target)
            current = target.stat(follow_symlinks=False)
            if not _same_artifact_identity(initial, current):
                raise RuntimeError(f"Published artifact {target.name!r} changed at preflight")
            preimage_statuses[target] = initial
            descriptor, rollback_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".rollback",
            )
            rollback = Path(rollback_name)
            rollback_paths[target] = rollback
            try:
                os.fchmod(descriptor, stat.S_IMODE(initial.st_mode))
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(preimage)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                with suppress(OSError):
                    os.close(descriptor)
                raise
        root = HERE.stat()
        for target, temporary in temporary_paths.items():
            rollback = rollback_paths[target]
            recovery_entries[target] = {
                "target": target.name, "temporary": temporary.name,
                "rollback": rollback.name if rollback is not None else None,
                "displaced": _unused_artifact_transaction_path(target, ".displaced").name,
                "failed": _unused_artifact_transaction_path(target, ".failed").name,
                "original_binding": _artifact_binding(target) if rollback is not None else None,
                "candidate_binding": _artifact_binding(temporary),
                "rollback_binding": _artifact_binding(rollback) if rollback is not None else None,
            }
            original_binding = recovery_entries[target]["original_binding"]
            initial = preimage_statuses[target]
            if original_binding is not None and initial is not None and (
                tuple(original_binding[key] for key in ("device", "inode", "bytes", "mtime_ns"))
                != (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)
                or original_binding["sha256"] != recovery_entries[target]["rollback_binding"]["sha256"]
            ):
                raise RuntimeError(f"Published artifact {target.name!r} changed while preparing recovery")
        recovery = {
            "version": 1, "transaction": secrets.token_hex(24), "state": "pending",
            "root": {"device": root.st_dev, "inode": root.st_ino},
            "artifacts": list(recovery_entries.values()),
        }
        _write_artifact_recovery(recovery)
        try:
            for target, temporary in temporary_paths.items():
                candidate_status = temporary.stat(follow_symlinks=False)
                preimage_status = preimage_statuses[target]
                displaced: Path | None = None
                try:
                    if preimage_status is not None:
                        displaced = HERE / recovery_entries[target]["displaced"]
                        target.rename(displaced)
                        moved_status = displaced.stat(follow_symlinks=False)
                        rollback = rollback_paths[target]
                        assert rollback is not None
                        if (
                            not _same_artifact_identity(preimage_status, moved_status)
                            or _read_regular_bytes_once(displaced)
                            != _read_regular_bytes_once(rollback)
                        ):
                            restoring, displaced = displaced, None
                            _restore_displaced_artifact(restoring, target)
                            raise RuntimeError(
                                f"Published artifact {target.name!r} changed before publication",
                            )
                    os.link(temporary, target, follow_symlinks=False)
                    # Once linked, rollback owns this candidate even when its first
                    # identity check fails. Bind the expected inode before any
                    # fallible observation; rollback conditionally preserves races.
                    published[target] = (candidate_status, candidate_bytes[target])
                    installed = target.stat(follow_symlinks=False)
                    if not _same_artifact_identity(candidate_status, installed):
                        raise RuntimeError(
                            f"Published artifact {target.name!r} changed during publication",
                        )
                    temporary.unlink()
                except Exception:
                    if displaced is not None and target not in published:
                        restoring, displaced = displaced, None
                        _restore_displaced_artifact(restoring, target)
                    raise
                finally:
                    if displaced is not None:
                        displaced.unlink(missing_ok=True)

            directory_descriptor = os.open(HERE, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
            for target in published:
                if not _artifact_matches(target, recovery_entries[target]["candidate_binding"]):
                    raise RuntimeError(
                        f"Published artifact {target.name!r} changed before commit",
                    )
            recovery["state"] = "committed"
            committing = True
            _write_artifact_recovery(recovery)
        except Exception as publication_error:
            if committing:
                # The marker may already be durable. Leave both generations in
                # custody; restart follows whichever complete WAL state survived.
                retain_rollback = True
                raise
            rollback_errors = _rollback_published_artifacts(
                published,
                rollback_paths,
                recovery_entries,
            )
            if isinstance(publication_error, _ArtifactRestoreError):
                rollback_errors.insert(0, str(publication_error))
            if rollback_errors:
                retain_rollback = True
                raise RuntimeError(
                    "Audit artifact publication failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                    + "; original preimages retained in .rollback files",
                ) from publication_error
            raise
    finally:
        active_recovery = (HERE / ARTIFACT_RECOVERY_NAME).exists()
        if active_recovery and not retain_rollback:
            _fsync_artifact_directory()
        for temporary in temporary_paths.values():
            temporary.unlink(missing_ok=True)
        for rollback in rollback_paths.values():
            if rollback is not None and not retain_rollback:
                rollback.unlink(missing_ok=True)
        if active_recovery and recovery is not None and not retain_rollback:
            _fsync_artifact_directory()
            (HERE / ARTIFACT_RECOVERY_NAME).unlink()
            _fsync_artifact_directory()


def _same_artifact_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


def _unused_artifact_transaction_path(target: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=suffix,
    )
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


class _ArtifactRestoreError(RuntimeError):
    """A displaced artifact remains in custody because restoration failed."""


def _restore_displaced_artifact(displaced: Path, target: Path) -> None:
    """Take custody of a moved name; delete it only after a successful restore."""
    try:
        os.link(displaced, target, follow_symlinks=False)
        displaced.unlink(missing_ok=True)
    except OSError as exc:
        raise _ArtifactRestoreError(
            f"{target.name}: displaced artifact retained at {displaced}; "
            f"restoration failed: {exc}",
        ) from exc


def _rollback_published_artifacts(
    published: dict[Path, tuple[os.stat_result, bytes]],
    rollback_paths: dict[Path, Path | None],
    recovery_entries: dict[Path, dict] | None = None,
) -> list[str]:
    """Rollback installed candidates only while their exact identity remains public."""
    errors: list[str] = []
    for target in reversed(published):
        expected_status, expected_payload = published[target]
        displaced: Path | None = (
            HERE / recovery_entries[target]["failed"] if recovery_entries is not None
            else _unused_artifact_transaction_path(target, ".failed")
        )
        try:
            try:
                target.rename(displaced)
            except FileNotFoundError:
                errors.append(f"{target.name}: published artifact was removed concurrently")
                continue
            moved_status = displaced.stat(follow_symlinks=False)
            if (
                not _same_artifact_identity(expected_status, moved_status)
                or _read_regular_bytes_once(displaced) != expected_payload
            ):
                restoring, displaced = displaced, None
                _restore_displaced_artifact(restoring, target)
                errors.append(f"{target.name}: published artifact changed before rollback")
                continue
            rollback = rollback_paths[target]
            if rollback is not None:
                try:
                    os.link(rollback, target, follow_symlinks=False)
                except FileExistsError:
                    errors.append(f"{target.name}: concurrent edit prevented rollback")
        except Exception as exc:
            errors.append(f"{target.name}: {exc}")
            if displaced is not None:
                restoring, displaced = displaced, None
                try:
                    _restore_displaced_artifact(restoring, target)
                except _ArtifactRestoreError as restore_error:
                    errors.append(str(restore_error))
        finally:
            if displaced is not None:
                displaced.unlink(missing_ok=True)
    return errors


def main() -> None:
    """Build, scan, and publish a complete candidate without pre-gate live writes."""
    recover_artifact_publication()
    (
        _manifest,
        manifest_bytes,
        verified_source_payloads,
        verified_source_bundles,
    ) = verify_live_inputs_against_manifest()
    with tempfile.TemporaryDirectory(
        dir=HERE,
        prefix=".reader-mode-audit-build.",
    ) as temporary_root_name:
        temporary_root = Path(temporary_root_name)
        temporary_root.chmod(0o700)
        input_dir = temporary_root / "inputs"
        stage_dir = temporary_root / "stage"
        materialize_verified_inputs(input_dir, verified_source_payloads)
        stage_dir.mkdir(mode=0o700)
        staged_manifest = stage_dir / INPUT_MANIFEST.name
        with staged_manifest.open("xb") as stream:
            stream.write(manifest_bytes)
        staged_manifest.chmod(0o600)

        executed = execute_notebook(
            notebook,
            input_dir=input_dir,
            output_dir=stage_dir,
        )
        nbformat.write(executed, stage_dir / NOTEBOOK.name)

        staged_manifest_bytes = _read_regular_bytes_once(staged_manifest)
        if staged_manifest_bytes != manifest_bytes:
            raise RuntimeError("Notebook execution changed the pinned input manifest")
        candidate_bytes = read_staged_candidate_bytes(stage_dir)

        private_full_identifiers, public_full_identifiers = (
            repository_identifiers_by_visibility(verified_source_bundles)
        )
        if len(private_full_identifiers) != 84:
            raise RuntimeError(
                "Expected 84 private repository identifiers, "
                f"found {len(private_full_identifiers)}",
            )
        private_only_slugs = private_only_repository_slugs(
            private_full_identifiers,
            public_full_identifiers,
        )
        private_reference_pattern = repository_reference_pattern(
            private_full_identifiers,
            private_only_slugs,
            public_full_identifiers,
        )
        publication_count = privacy_gate_candidate_bytes(
            candidate_bytes,
            manifest_bytes=manifest_bytes,
            private_reference_pattern=private_reference_pattern,
        )
        publish_exact_candidate_bytes(candidate_bytes)

    print(f"Executed {NOTEBOOK}")
    print(
        f"Privacy gate passed for {publication_count} public files against "
        f"{len(private_full_identifiers)} private repository identifiers and "
        "all private-only bare-slug forms",
    )


if __name__ == "__main__":
    main()
