---
name: quantum-info-literature-search
description: physics literature-search workflow for quantum information and adjacent theory domains. use when chatgpt should help a researcher map a field, refine a literature-search strategy, identify credible and recent papers, expand from seed papers or questions, compare authors/labs/journals, or build a reading list with explicit conditional iteration. especially useful for warm searches from known papers and cold searches from loosely defined research questions, and when outputs should incorporate citation strength, venue/lab reputation, recency, and limited social-signal checks such as x or researcher discussion.
---

# Quantum Info Literature Search

## Overview

Use this skill to help physics researchers run an explicit, conditionally iterative literature search in quantum information. Treat the task as field mapping plus decision support, not just keyword retrieval.

Optimize for four things at the same time:
1. topical relevance,
2. scientific credibility,
3. recency,
4. efficient expansion paths.

Prefer a workflow that starts from either a seed paper or a draft research question, then loops through search, screening, reading, expansion, and synthesis until the marginal yield becomes low.

## Default workflow

Follow this order unless the user asks for only one subtask.

1. Determine the entry mode.
   - **Warm search**: the user already has a paper, author, lab, result, or venue.
   - **Cold search**: the user has a topic or question but no reliable seed paper.
   - **Hybrid**: use both when the user gives a rough question plus one or two anchor papers.
2. Run a broad scoping pass.
3. Learn and normalize the field vocabulary.
4. Screen titles and abstracts.
5. Read the highest-yield papers first.
6. Expand through citations, authors, labs, and journals.
7. Track notes and references in external scholarly tools.
8. Decide whether to narrow, broaden, branch, or stop.

Make the loop explicit in your response. Do not present the workflow as a single fixed linear chain.

## Workflow decision tree

### Step 1: choose the entry mode

**If the user starts from a known paper, author, or lab:**
- Treat it as a warm search.
- Extract searchable signals from the seed:
  - title and subtitle language,
  - author names,
  - lab or collaboration,
  - journal or conference,
  - arxiv category if visible,
  - method keywords,
  - mathematical objects, models, or tasks.
- Decide whether the seed is:
  - foundational,
  - recent frontier work,
  - a review,
  - an outlier,
  - adjacent but not central.

**If the user starts from a topic or problem statement:**
- Treat it as a cold search.
- Rewrite the topic as a searchable research question with:
  - phenomenon or subfield,
  - formalism or method,
  - system class,
  - target outcome,
  - optional timeframe.
- Generate a first-pass list of terms:
  - canonical field terms,
  - synonyms,
  - older terminology,
  - adjacent-subfield language.

**If the entry point is weak or obviously off-target:**
- Do not over-anchor.
- Use it only to bootstrap vocabulary, then broaden quickly.

## Step 2: broad scoping search

In the scoping pass, aim to map the literature landscape rather than build the final bibliography.

Do the following:
- Search with a few short, high-recall queries.
- Pull a balanced set of papers:
  - at least one review or perspective when available,
  - several recent papers,
  - several highly cited older papers,
  - at least one paper from a clearly respected venue or group.
- Look for repeated patterns:
  - recurring authors,
  - recurring labs or institutes,
  - recurring journals,
  - recurring mathematical frameworks,
  - recurring keywords in titles and abstracts.

For quantum information, pay attention to whether the literature cluster is really about the intended topic or is drifting into one of the nearby zones:
- quantum foundations,
- condensed matter / many-body,
- AMO implementation papers,
- cryptography,
- quantum computing architecture,
- quantum error correction,
- quantum communication,
- quantum algorithms,
- quantum complexity,
- quantum thermodynamics.

## Step 3: learn the field vocabulary

Translate the user's wording into the field's wording.

Build a vocabulary map with four columns:
1. the user's original wording,
2. canonical terms used by the field,
3. narrower technical terms,
4. nearby but non-equivalent terms.

In quantum information, explicitly watch for vocabulary drift across theory, math, and experiment. Terms that look similar may carry different technical commitments.

Use vocabulary refinement to improve later search strings.

**If search results are noisy:**
- add one disambiguating concept,
- restrict by method, task, or system class,
- separate theory and experiment branches.

**If search results are sparse:**
- widen to adjacent terminology,
- remove one constraint,
- search older language or related subfields.

## Step 4: screen titles and abstracts

Use a lightweight triage pass before deep reading.

Classify each paper into one of four bins:
- **core**: directly relevant and likely important,
- **supporting**: relevant background or method,
- **branch**: interesting adjacent direction,
- **drop**: not useful for the present question.

Assess each paper against these criteria:
- Is it actually about the target question?
- Is it theory, experiment, review, methods, or commentary?
- Does it introduce a new result, synthesize a field, or merely apply known machinery?
- Is it from a credible venue, author group, or collaboration?
- Is it recent enough for the user's purpose?
- Does it appear to be influential or widely used?

Do not rely on any single prestige signal. A strong result may be important even if it is new, niche, or currently under-cited.

## Step 5: read the most relevant papers

Read the highest-yield papers first rather than reading chronologically.

Recommended priority order:
1. review or perspective papers,
2. seminal older papers that define the problem or method,
3. recent frontier papers,
4. direct methodological neighbors,
5. branch papers only if they keep reappearing.

For each paper, extract:
- core problem,
- exact claim or theorem/result,
- assumptions,
- method or formalism,
- evidence type,
- relationship to prior work,
- limitations,
- why it matters for the user's question.

Also assess the paper using four evaluation lenses.

### 5A. Credibility and popularity

Use these signals cautiously and in combination:
- citation count or citation velocity,
- respected venue,
- respected author or lab,
- whether the paper is repeatedly treated as foundational or standard in later work,
- whether multiple independent groups build on it.

For physics, treat citations as one indicator, not a verdict. Older theoretical papers often accumulate prestige slowly; newer arxiv-first work may be important before formal citation counts catch up.

### 5B. Recency

Ask whether the user needs:
- historical foundations,
- current frontier papers,
- both.

For fast-moving subtopics, emphasize the past two to five years without discarding indispensable older papers.

### 5C. Venue and author/lab context

Record where the work sits socially and institutionally:
- journal or proceedings venue,
- author track record,
- lab or collaboration reputation,
- whether the work appears in a recognized research stream.

Use this to prioritize reading order, not to dismiss contrarian or new work automatically.

### 5D. Social channels such as x

Treat x or similar channels as a weak, supplementary signal only.

Use social discussion to detect:
- what people are paying attention to right now,
- informal community reception,
- notable critiques, excitement, or confusion,
- which recent preprints are being circulated.

Do **not** treat social attention as evidence of correctness. Use it to prioritize what to inspect, especially for recent arxiv papers that have not yet accumulated citations.

## Step 6: expand beyond citations

Do not expand only through references and forward citations.

Use four expansion channels in parallel.

### 6A. Citations and references
- backward search for foundational work,
- forward search for follow-up papers, critiques, replications, or extensions,
- lateral search for sibling papers that share methods or assumptions.

### 6B. Author expansion
- follow the same author across related papers,
- identify recurring coauthor clusters,
- distinguish between a one-off application and a sustained research program.

### 6C. Lab or group expansion
- follow labs, institutes, or collaborations that repeatedly appear,
- inspect whether a group is setting a local vocabulary or agenda,
- compare how different groups treat the same problem.

### 6D. Journal or venue expansion
- inspect journals or proceedings where the topic repeatedly appears,
- use venue patterns to separate mature subliteratures from emerging ones,
- note whether the same topic is split between theory-heavy and experiment-heavy venues.

Treat expansion as branch management.

**If a branch repeatedly produces central papers:**
- deepen it.

**If a branch keeps drifting away from the question:**
- stop following it.

**If the same papers, labs, or venues appear through multiple paths:**
- mark them as central.

## Step 7: track notes and references carefully

Use external scholarly tools to keep the process reproducible.

Preferred tools for this skill:
- OpenAlex,
- Google Scholar,
- Semantic Scholar.

Use them for distinct purposes:
- **OpenAlex**: entity graphing, author/work/venue linking, structured metadata, citation-network navigation.
- **Google Scholar**: broad recall, quick relevance checks, forward citation browsing, rough popularity signals.
- **Semantic Scholar**: citation links, related-paper discovery, fast paper overviews, author and topic tracing.

For each saved paper, record at minimum:
- citation,
- one-sentence summary,
- relevance label,
- subfield tags,
- method or framework tags,
- credibility notes,
- recency notes,
- expansion paths to try next.

Also keep synthesis notes across papers:
- recurring claims,
- disputed points,
- standard methods,
- influential authors and labs,
- open problems or gaps.

## Step 8: iterate conditionally

At the end of every pass, explicitly decide what to do next.

### Narrow the search when:
- results are too noisy,
- multiple subfields are being mixed together,
- the user needs a focused reading list,
- theory and experiment need to be separated.

### Broaden the search when:
- too few papers survive screening,
- the query uses idiosyncratic language,
- adjacent subfields may contain the relevant formulation,
- the current literature cluster is too recent and lacks foundations.

### Branch the search when:
- one method family keeps recurring,
- one author or lab anchors many relevant results,
- a debate or contradiction appears repeatedly,
- a review paper reveals a subliterature that deserves its own track.

### Stop when:
- new searches mostly return already-known core papers,
- the same names, ideas, journals, and labs keep reappearing,
- additional papers add only marginal conceptual value for the user's purpose.

## Output pattern

Unless the user asks for a different format, structure your answer like this:

### Search map
- entry mode: warm / cold / hybrid
- current scope
- likely neighboring subfields

### Priority reading order
- tier 1: must-read papers
- tier 2: supporting or methodological papers
- tier 3: branch papers

### Why these papers matter
- relevance
- credibility / influence
- recency
- author / lab / venue context

### Next expansion moves
- citations to follow
- authors to follow
- labs to follow
- journals to inspect
- recent social-signal checks worth using cautiously

### Decision for the next loop
- narrow / broaden / branch / stop
- one-sentence rationale

## Style rules

- Make the iterative logic visible.
- Prefer concise judgments over generic praise.
- Distinguish clearly between evidence, prestige, and attention.
- For quantum information, preserve technical precision and do not flatten theory/experiment distinctions.
- When confidence is limited, say so explicitly.
- If the user wants a final reading list, bias toward papers that are both central and diversity-preserving across authors or groups.

## References in this skill

Use these bundled references when helpful:
- `references/workflow-map.md` for the expanded workflow with substeps.
- `references/scholarly-tools.md` for how to use OpenAlex, Google Scholar, and Semantic Scholar within the workflow.
