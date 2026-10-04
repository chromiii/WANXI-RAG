# Project 1 RAG Testing

Project 1 uses two complementary test layers:

1. **Deterministic regression tests** — code-level contracts that must always pass.
2. **Business acceptance evaluation** — fixed end-to-end RAG cases against the real local index, optionally with live DeepSeek generation.

The goal is not to assign a fake automatic score to subjective writing quality. The suite focuses on failure modes that can be checked deterministically: intent routing, hallucination guards, citation closure, PDF provenance, chunk boundaries, post-retrieval filtering, output schemas and early-stop behavior.

## 1. Regression suite

Run only Project 1 tests:

```powershell
py -m unittest discover -s tests -p "test_project1_*.py" -v
```

Run the full repository suite:

```powershell
py -m unittest discover -s tests -v
```

The CI workflow runs the full suite on every push.

### Test files

| File | Main coverage |
| --- | --- |
| `test_project1_intent.py` | scope guard, meta intent, explicit/auto content type, semantic focus, original-question preservation |
| `test_project1_grounding.py` | unknown citations, empty citations, numeric hallucination, hypothetical-case misuse, unsupported guarantees, publishable prose |
| `test_project1_pdf.py` | physical page preservation, page renders, sparse pages, repeated boilerplate, stable chunk IDs, max chunk length, no cross-page merge |
| `test_project1_postprocess.py` | hard safety filter, hypothetical handling, reranker-order preservation, near-duplicate removal, Top-N backfill, context budget |
| `test_project1_generation.py` | four writer schema contracts, standalone FAQ behavior, three extension FAQs, markdown order, visual provenance |
| `test_project1_evidence_gate.py` | generic evidence sufficiency contract, no-hit behavior, offline passthrough, arbitrary missing facts |

PDF tests generate temporary synthetic PDFs in the test process. Employer PDF content is not committed to GitHub.

## 2. Business acceptance cases

Cases are stored in a single shared catalog:

```text
eval/project1_cases.json
```

The evaluator, CLI `demo` command and Web quick-case buttons all read this same catalog.

The current matrix includes:

- official Blog topic;
- customer-problem FAQ;
- brand introduction;
- product introduction;
- product-format/original-question conflict;
- unknown financial fact;
- prompt-injection/fabrication request;
- unrelated travel request;
- meta greeting;
- hypothetical招商银行 scenario.

Run with deterministic offline generation:

```powershell
py scripts/eval_project1.py --mode offline
```

Run the same cases with live DeepSeek generation:

```powershell
py scripts/eval_project1.py --mode live
```

Run one category:

```powershell
py scripts/eval_project1.py --mode live --category hallucination
```

Run one case:

```powershell
py scripts/eval_project1.py --mode live --case official_blog
```

Require the local normalized PDF artifacts to pass integrity checks:

```powershell
py scripts/eval_project1.py --mode live --require-pdf-artifacts
```

Reports are written to the private runtime directory:

```text
data/private/eval/project1_eval_offline.json
data/private/eval/project1_eval_live.json
```

They are runtime artifacts and are not committed.

## 3. What the evaluator checks

For successful generations it verifies:

```text
generated citation ids
        ⊆
references
        ⊆
retrieval_hits
```

It also checks:

- intent/content type and semantic focus;
- original FAQ question preservation;
- exactly three extension FAQs for Blog / brand / product outputs;
- no source-report phrases such as “资料显示” in publishable claims;
- numeric/citation grounding validator results;
- source visuals only come from cited references and are limited to three unique PDF pages;
- required workflow stages are present.

For early-stop cases it checks:

- prompt injection is rejected before generation;
- unrelated queries stop as `out_of_scope`;
- greetings/self-description use the meta route;
- live mode can return `insufficient_evidence` for arbitrary unsupported facts via the generic evidence sufficiency judge;
- early-stop cases do not unnecessarily call the LLM where applicable.

## 4. Runtime PDF integrity checks

When normalized private artifacts are available, the evaluator checks:

- normalized evidence is non-empty;
- chunk IDs are unique and match `pdf-pNNN-cNN`;
- content stays within configured `max_chars`;
- all page numbers are valid physical pages;
- all chunks refer to one source SHA-256;
- source block IDs never cross physical page boundaries;
- linked page-render assets exist.

The lower-level synthetic PDF tests additionally verify boilerplate removal, sparse page handling and full-page visual rendering.

## 5. Hallucination strategy tested

The suite distinguishes several hallucination classes:

1. **Citation hallucination** — generated citation ID does not exist.
2. **Numeric hallucination** — output introduces a number absent from cited evidence.
3. **Case-status hallucination** — an application hypothesis becomes a delivered client case.
4. **Guarantee hallucination** — unsupported recommendation/ranking/growth guarantee.
5. **Missing-fact hallucination** — user asks for a specific fact not present in the source; the live evidence-sufficiency judge is generic rather than tied to a revenue/funding field list.
6. **Presentation hallucination** — Writer fills unsupported product sections merely to satisfy a schema.

These checks complement, but do not claim to prove, full semantic entailment.

## 6. Recommended submission evidence

For the final demo, keep three artifacts:

1. terminal showing the regression suite passing;
2. `project1_eval_live.json` generated locally;
3. browser demo showing citations, source visuals and workflow trace.

This gives reviewers both engineering regression evidence and an end-to-end business acceptance demonstration.
