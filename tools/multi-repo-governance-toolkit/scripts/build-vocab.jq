def enums: ["status","documentation_status","promotion_status","tier","implementation_status","ci_workflow","functional_class","type","revenue_model","revenue_status"];

# Flat stream of {term, category, source} from every canonical-name surface.
[
  (.organs | to_entries[] | {term: .key, category: "organ", source: "organs.<id>"}),
  (.organs | to_entries[] | {term: .value.name, category: "organ_name", source: ("organs." + .key + ".name")}),
  (.organs[].repositories[]? | {term: .org, category: "organization", source: "repositories[].org"}),
  (.organs[].repositories[]? | {term: .name, category: "repository", source: "repositories[].name"}),
  (.organs[].repositories[]? as $r | enums[] as $f | select($r[$f] != null and $r[$f] != "") | {term: ($r[$f] | tostring), category: ("enum:" + $f), source: ("repositories[]." + $f)})
]
| map(select(.term != null and .term != ""))
| group_by([.category, .term])
| map({term: .[0].term, category: .[0].category, synonyms: [], sources: (map(.source) | unique)})
| sort_by(.category, .term) as $terms
| ($terms | group_by(.category) | map({key: .[0].category, value: length}) | from_entries) as $counts
| {
    schema_version: "0.1.0",
    irf: "IRF-RES-006",
    slice: "1 of 3 — canonical name extraction",
    generated_by: "scripts/build-vocab.py",
    source: "registry-v2.json",
    purpose: "Controlled vocabulary registry for ORGANVM domain terms. Slice 1 extracts canonical names from the registry. Synonymy reconciliation (slice 2) and CI validation hook (slice 3) are deferred.",
    deferred: [
      "synonymy-reconciliation — populate each term's synonyms[] (slice 2)",
      "ci-validation-hook — reject off-vocabulary names in CI (slice 3)"
    ],
    term_count: ($terms | length),
    category_counts: $counts,
    terms: $terms
  }
