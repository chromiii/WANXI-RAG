# Submission Checklist

Use this checklist before sending the Project 1 repository and Demo.

## Repository

- [ ] README opens with the Project 1 goal and architecture.
- [ ] docs/INSTALL.md reproduces the local setup from a clean clone.
- [ ] docs/DEMO.md matches the recorded demo flow.
- [ ] No private PDF, parsed evidence, page image, evaluation report or run log is tracked.
- [ ] No populated .env, API key, token or credential is tracked.
- [ ] Generated examples/ output is not tracked.
- [ ] CI on main is green.

## Code validation

Run:

~~~powershell
py -m unittest discover -s tests -v
py -m compileall -q trendee
~~~

Expected: all tests pass.

## Real-data validation

With the authorized PDF, Elasticsearch and DeepSeek key available:

~~~powershell
docker compose up -d elasticsearch
py -m trendee.cli index-info
py -m trendee.cli info
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

Expected: the selected acceptance suite passes and the runtime PDF integrity check passes.

The generated report stays local:

~~~text
data/private/eval/project1_eval_live.json
~~~

## Demo validation

Before recording:

~~~powershell
py -m trendee.cli serve
~~~

Open http://127.0.0.1:8000 and verify:

- Intent & Run renders correctly.
- Query Plan preserves the original query.
- Evidence Clues show page/chunk provenance.
- PDF source page images open.
- Generated Content renders citations.
- Evidence Sufficiency stops an unsupported fact request.
- Grounding validation is visible.
- Recent local logs can be opened without exposing credentials.

## Suggested delivery

Send:

1. GitHub repository link;
2. Demo video;
3. any written answer/document requested by the recruiter.

Keep private runtime artifacts out of the public repository. If the recruiter needs the original PDF or generated evaluation report, send them only through the channel they provided.

## Final repository sanity check

From the repository root:

~~~powershell
git status
git ls-files
~~~

Review the tracked file list. There should be no:

~~~text
.env
data/private/
examples/
*.pdf
API keys
Elasticsearch data
Hugging Face model weights
run logs
live evaluation reports
~~~

If a secret was ever committed, removing it from the latest file is not sufficient; rotate the key and remove it from repository history before submission.
