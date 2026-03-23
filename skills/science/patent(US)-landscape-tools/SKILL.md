---
name: patent-landscape-tools
description: Drug-patent landscape workflow guide for searching US patents via the PatentsView API, classifying pharmaceutical claim types (NCE, formulation, method-of-use, polymorph, combination, biologic, process), grouping by patent family and assignee, estimating expiry timelines, and cross-referencing the FDA Orange Book for marketed-drug exclusivity windows. Use when the user asks about patent coverage, IP white-space, patent cliffs, or competitive filing activity around a drug, target, or compound class without asking for legal counsel.
---

# Patent Landscape Tools

Use this skill for research-grade patent intelligence around drugs, targets, or mechanisms, not legal freedom-to-operate opinions.

Typical triggers:
- search US patents related to a drug compound, target, or mechanism of action
- classify pharmaceutical patents by claim type: NCE, formulation, method-of-use, polymorph, biologic, process
- build a landscape summary showing filing trends, top assignees, and claim-type distribution
- estimate patent expiry windows for one or more patent families
- cross-reference the FDA Orange Book for a marketed drug's listed patents and exclusivity codes
- identify IP white-space or under-patented mechanism classes before a new filing strategy

## Working Rules

1. Always apply a pharmaceutical CPC filter (A61K, A61P, or C07) to avoid non-drug noise.
2. Distinguish granted patents from applications; PatentsView covers grants only.
3. Report the data source, query date, and coverage limitation (US-only) in every output.
4. Claim-type classification is heuristic from title and abstract keywords, not from reading claims.
5. Expiry is estimated as filing date + 20 years; PTE, PTA, SPC, and terminal disclaimers are not computed.
6. Do not present any output as freedom-to-operate analysis, legal advice, or infringement opinion.

## Environment Check

```bash
which python3 || true
python3 - <<'PY'
mods = ["requests"]
for name in mods:
    try:
        __import__(name)
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: missing ({exc})")
PY
```

If network access is unavailable, say so before claiming patent data was retrieved.

## Bundled Assets

- `templates/patent_landscape.py`

## Patent Landscape Search

Use `templates/patent_landscape.py` for:
- keyword + CPC-filtered patent search on PatentsView
- automatic claim-type classification of each result
- assignee ranking, filing-trend extraction, and family grouping
- optional markdown landscape brief

Quick start:

```bash
python3 templates/patent_landscape.py \
  --query "KRAS G12C inhibitor" \
  --cpc-filter A61K \
  --max-results 200 \
  --output patents/kras_g12c_landscape.csv \
  --summary patents/kras_g12c_summary.json \
  --brief patents/kras_g12c_brief.md
```

Broad landscape with date range:

```bash
python3 templates/patent_landscape.py \
  --query "PD-1 antibody" \
  --cpc-filter A61K39 \
  --date-from 2015-01-01 \
  --max-results 500 \
  --output patents/pd1_ab_landscape.csv \
  --summary patents/pd1_ab_summary.json
```

Deliverables:
- per-patent CSV with patent number, title, filing date, grant date, assignee, country, CPC, claim-type guess, estimated expiry year, and abstract snippet
- summary JSON with total count, estimated family count, claim-type distribution, top assignees, country distribution, filing-year trend, and expiry window
- optional markdown brief with tables and caveats

## Expiry Timeline

Use `templates/patent_landscape.py --mode expiry-timeline` for:
- patent expiry estimation sorted by earliest expiry
- identification of upcoming patent cliffs for a compound or class

```bash
python3 templates/patent_landscape.py \
  --query "semaglutide" \
  --mode expiry-timeline \
  --output patents/semaglutide_expiry.csv \
  --summary patents/semaglutide_expiry.json
```

Deliverables:
- patent CSV sorted by estimated expiry year
- summary JSON with total patents and timeline entry count

## Orange Book Cross-Reference

Use `--orange-book-query` to add FDA Orange Book data for a marketed drug:

```bash
python3 templates/patent_landscape.py \
  --query "semaglutide" \
  --mode expiry-timeline \
  --orange-book-query "semaglutide" \
  --output patents/semaglutide_expiry.csv \
  --summary patents/semaglutide_expiry.json
```

Orange Book entries include: brand name, generic name, NDA number, dosage form, route, and marketing status.

## CPC Filter Reference

| CPC | Scope |
|-----|-------|
| A61K | Pharmaceutical compositions (broadest drug filter) |
| A61K31 | Small-molecule active ingredients |
| A61K39 | Antibodies, vaccines, antigens |
| A61K47 | Excipients, carriers, formulation technology |
| A61P | Therapeutic activity by indication |
| C07D | Heterocyclic compounds (core scaffolds) |
| C07K | Peptides and proteins |

## Claim-Type Classification Heuristics

The template matches title + abstract keywords to assign one of:
- `NCE / composition-of-matter` — compound, molecule, chemical entity, active ingredient
- `formulation` — dosage form, tablet, capsule, nanoparticle, sustained release
- `method-of-use` — method of treating, therapeutic use, for the treatment
- `polymorph / salt form` — polymorph, crystal form, salt, co-crystal, hydrate
- `combination` — combination, co-administration, synergistic
- `biologic` — antibody, recombinant, fusion protein, monoclonal
- `diagnostic` — biomarker, companion diagnostic, imaging agent
- `device / delivery` — device, inhaler, auto-injector, applicator
- `process / manufacturing` — synthesis, preparation, method of making

First match wins. Unmatched patents are labeled `unclassified`. This is not claim analysis.

## Output Expectations

Good answers should mention:
- the query terms, CPC filter, and date range applied
- number of patent families and individual documents retrieved
- claim-type distribution
- top assignees with filing counts
- filing trend by year
- estimated expiry window for key families
- Orange Book listings if queried
- explicit caveat: US patents only, heuristic classification, not legal counsel
- where the CSV, JSON, and optional brief were saved

## Related Skills

For compound and regulatory lookups from ChEMBL, openFDA, ClinicalTrials.gov, activate `pharma-db-tools`.
For target-level intelligence dossiers, activate `target-intelligence-tools`.
For clinical-pipeline competitive analysis, activate `competitive-intelligence-tools`.
For drug repurposing hypothesis generation, activate `drug-repurposing-tools`.

## Reference

This skill queries the following public APIs:
- **USPTO PatentsView API** — `https://api.patentsview.org/patents/query` — US granted-patent search with CPC, date, and full-text filters ([patentsview.org/apis](https://patentsview.org/apis))
- **FDA openFDA drugsFDA API** — `https://api.fda.gov/drug/drugsfda.json` — Orange Book product listings including brand/generic names, NDA numbers, dosage forms, and marketing status ([open.fda.gov/apis/drug/drugsfda](https://open.fda.gov/apis/drug/drugsfda/))
- **CPC classification scheme** — Cooperative Patent Classification maintained by EPO and USPTO; A61K/A61P/C07 subclasses are used as pharmaceutical relevance filters ([cooperativepatentclassification.org](https://www.cooperativepatentclassification.org/))
- Claim-type classification heuristics are adapted from pharmaceutical IP landscape methodology described in: Dubey R, Maheshwari S. "Patent landscape analysis: A methodology for drug discovery." *Drug Discovery Today*, 2020.