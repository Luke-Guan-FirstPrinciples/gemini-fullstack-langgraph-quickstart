# Product Requirements Document

## Title

Any-to-Any Research Literature Retrieval and Ranking

## Status

Draft

## Author

L G

## Date

2026-04-01

---

## 1. Overview

This document defines a product for **any-to-any research literature and information retrieval**. The system enables users to start from multiple kinds of research inputs—such as a paper, author, lab, topic, or free-form query—and retrieve relevant research entities across those same entity types.

The product is designed around a two-stage loop:

1. **Retrieval** of candidate entities and documents.
2. **(Re-)ranking** of those candidates using signals such as popularity, credibility, recency, and relatedness.

The initial implementation should prioritize integration with **LLMs** and **OpenAlex**.

---

## 2. Problem Statement

Research discovery is fragmented across search engines, citation graphs, author pages, lab websites, and topic-based queries. Existing tools typically optimize for one mode of discovery at a time:

* keyword search,
* citation traversal,
* author lookup,
* or paper recommendations.

Researchers need a unified system that supports **flexible entry points** and **cross-entity discovery**. For example, users should be able to:

* start from a paper and find related authors, labs, and topics, trace citation both up stream and downstream
* start from an author and find their most relevant papers or adjacent labs, collaboration network
* start from a topic and find foundational papers, current work, and leading groups, most recent paper
* start from a query and navigate across the literature ecosystem with high-quality ranking.

Without this, discovery is slower, less systematic, and biased toward whichever search surface the user happens to start from.

---

## 3. Product Vision

Build a research discovery engine that allows users to move seamlessly between **papers, authors, labs, topics, and natural-language queries**, with retrieval and ranking that surfaces the most useful and trustworthy results for a given research task.

---

## 4. Goals

### Primary Goals

* Support **any-to-any retrieval** across the core research entities:

  * Paper
  * Author
  * Lab
  * Topic
  * Query
* Combine **broad candidate retrieval** with **high-quality re-ranking**.
* Rank results using a mix of:

  * popularity,
  * credibility,
  * recency,
  * topical relatedness,
  * citation relatedness,
  * hierarchical relatedness.
* Create a system that is useful for both:

  * exploratory literature review,
  * and targeted information retrieval.

### Secondary Goals

* Use LLMs to improve query understanding, entity normalization, expansion, summarization, and ranking support.
* Use OpenAlex as the initial structured literature backbone for works, authors, institutions, concepts, and citation metadata.
* General-purpose web search outside research-related content 
* Provide a modular architecture so additional sources can be added later.

---

## 5. Non-Goals

* Full-text hosting of papers.
* End-to-end lab intelligence beyond what can be inferred from research metadata.
* Personalized recommendations in the first release.
* Building a new citation database from scratch. (Use OpenAlex for citation data)

---

## 6. Target Users

### Primary Users

* AI Agent
* Researchers conducting literature reviews.
* Research engineers mapping a new area.
* Analysts evaluating authors, labs, or research directions.
* Technical teams doing domain-specific information retrieval.

### Secondary Users

* Students exploring a field.
* Product or strategy teams scanning research ecosystems.
* Recruiting or partnership teams identifying labs and authors.

---

## 7. User Jobs To Be Done

* “Given this paper, show me the most relevant adjacent papers, authors, and labs.”
* “Given this author, show me their key papers, collaborators, affiliated lab, and nearby topics.”
* “Given this lab, show me what they are known for, their recent work, and related groups.”
* “Given this topic, show me canonical papers, recent momentum, and top researchers.”
* “Given this natural-language query, map me into the relevant literature landscape.”
* “Help me discover not just what is most cited, but what is most credible, relevant, and recent.”

---

## 8. Core Product Concept

The product supports **entity-to-entity traversal**. Any supported input type can become the starting point for retrieval, and the output can include one or more supported entity types.

### Supported Input Types

* Paper
* Author
* Lab
* Topic
* Free-form query

### Supported Output Types

* Paper
* Author
* Lab
* Topic
* Query refinement / suggested follow-up queries

### Conceptual Flow

1. User provides one starting entity or query.
2. System normalizes the input into one or more canonical entities.
3. Retrieval system gathers candidate related entities.
4. Re-ranking system scores candidates using multiple signals.
5. UI presents ranked outputs and allows iterative traversal.
6. User clicks a result and repeats the loop from that new node.

---

## 9. Key Product Requirements

### 9.1 Entity Resolution and Normalization

The system must:

* resolve papers from title, DOI, URL, or citation text,
* resolve authors despite naming ambiguity,
* map labs to institutions, groups, or recurring collaboration clusters where possible,
* map topics to structured concepts and embeddings,
* parse free-form queries into likely entities and retrieval intents.

### 9.2 Retrieval Layer

The system must retrieve candidate results for each input type.

Examples:

* **Paper → Papers** via citation links, co-citation, bibliographic coupling, embeddings, and concept overlap.
* **Paper → Authors** via author metadata, related collaborators, and nearby citation neighborhoods.
* **Paper → Labs** via institutional and collaboration inference.
* **Author → Papers** via authored works, highly cited works, recent works, and topic-relevant works.
* **Author → Authors** via coauthorship, topic similarity, and citation adjacency.
* **Topic → Papers** via concept matching, embedding retrieval, and OpenAlex concept associations.
* **Query → Everything** via LLM-assisted parsing and retrieval expansion.

### 9.3 Re-Ranking Layer

The system must re-rank retrieved candidates using a weighted scoring framework.

#### Core Ranking Signals

* **Popularity**: citations, influence, centrality, usage proxies.
* **Credibility**: venue quality, author reputation, institutional signal, consistency across sources.
* **Recency**: publication date and freshness relative to the user’s task.
* **Topical relatedness**: semantic similarity, concept overlap, embedding proximity.
* **Citation relatedness**: direct citations, co-citations, bibliographic coupling, citation graph distance.
* **Hierarchical relatedness**: broader-to-narrower topic relations and entity clustering.

#### Ranking Principles

* The ranking system should not overfit to citation count alone.
* Users should be able to bias ranking toward exploratory depth, recent work, or canonical work.
* Ranking explanations should be exposed where practical.

### 9.4 Iterative Discovery Loop

The product must support recursive exploration.

* Any result should become a new starting node.
* Retrieval and re-ranking should rerun on each step.
* The system should preserve path context so users understand how they arrived at a result.

### 9.5 Explainability

For each result, the system should provide compact explanations such as:

* “Highly cited in this topic”
* “Recent work from a leading lab”
* “Frequently co-cited with the seed paper”
* “Semantically close to your query”

### 9.6 Source Prioritization

The first integrations to prioritize are:

1. **OpenAlex** for structured scholarly metadata and graph relationships.
2. **LLMs** for query interpretation, expansion, summarization, disambiguation, and ranking assistance.

---

## 10. Functional Requirements

### FR1. Search and Input Handling

* User can enter a paper title, DOI, author name, lab name, topic, or free-form query.
* System identifies probable entity type automatically.
* System asks for disambiguation when confidence is low.

### FR2. Candidate Retrieval

* System retrieves a configurable number of candidates per entity type.
* Retrieval must support both graph-based and semantic methods.
* Retrieval latency should be acceptable for interactive use.

### FR3. Multi-Entity Outputs

* User can request outputs by entity class, such as only papers or only authors.
* System can also show mixed outputs grouped by entity type.

### FR4. Ranking Controls

* User can choose or adjust ranking presets such as:

  * Canonical
  * Recent
  * Credible
  * Related
  * Exploratory
* System stores the ranking mode for the current exploration session.

### FR5. Result Explanations

* Each result includes score contributors or reason labels.
* Top results should include at least one human-readable justification.

### FR6. Iteration and Navigation

* Clicking a result starts a new retrieval cycle from that entity.
* User can navigate backward through prior steps.
* Session state preserves path history.

### FR7. Summarization Support

* LLM can summarize the result set or explain the neighborhood of a paper, author, lab, or topic.
* LLM can propose follow-up queries.

### FR8. Data Freshness

* System should surface recent papers where relevant.
* Metadata refresh cadence should be defined for integrated sources.

---

## 11. Data and Integrations

### OpenAlex

OpenAlex should serve as the primary initial data source for:

* works,
* authors,
* institutions,
* concepts,
* citations,
* related scholarly metadata.

### LLMs

LLMs should be used for:

* query understanding,
* entity extraction,
* disambiguation,
* query expansion,
* topic labeling,
* result explanation,
* summarization,
* optional ranking assistance.

### Future Integrations

Potential later integrations may include:

* Semantic Scholar or Crossref,
* ArXiv / PubMed / domain-specific corpora,
* internal reading lists or saved collections,
* user feedback data for ranking refinement.

---

## 12. UX Requirements

### Primary Interface Elements

* Unified search/input bar.
* Entity-type detection and confirmation.
* Result tabs or groups by entity type.
* Ranking mode selector.
* Explanation chips under each result.
* Traversal breadcrumbs showing discovery path.

### UX Principles

* Minimize friction between starting points.
* Make graph traversal feel intuitive, not like separate tools.
* Preserve trust through transparent ranking signals.
* Encourage exploration without overwhelming the user.

---

## 13. Success Metrics

### Adoption and Engagement

* Number of searches per session.
* Number of iterative traversal steps per session.
* Percentage of sessions with multi-step exploration.

### Retrieval Quality

* Precision of top-k results for each retrieval mode.
* Entity resolution accuracy.
* Click-through rate on top-ranked results.

### Ranking Quality

* User-rated relevance of top results.
* Coverage across canonical, recent, and adjacent work.
* Reduction in time-to-find-useful-paper or time-to-map-topic.

### System Performance

* Median end-to-end latency.
* Retrieval latency by input type.
* Re-ranking latency by candidate set size.

---

## 14. Risks and Open Questions

* How should “lab” be represented when source data is institution-centric rather than lab-centric?
* What weight should citation signals receive versus semantic similarity for newer fields?
* How should credibility be operationalized without simply mirroring prestige bias?
* Should the first release optimize for mixed-entity discovery or paper-first workflows?
* Which ranking controls should be user-visible versus system-managed?
* How should the product handle ambiguous or under-specified queries?

---

## 15. MVP Scope

The MVP should include:

* Input support for paper, author, topic, and free-form query.
* Retrieval of papers and authors first, with labs as best-effort inferred entities.
* OpenAlex integration for metadata and graph retrieval.
* LLM support for parsing, expansion, and explanations.
* A basic re-ranking model using popularity, recency, and topical/citation relatedness.
* Iterative traversal from one result to the next.

### Out of Scope for MVP

* Deep personalization.
* Collaborative workflows.
* Full lab knowledge graph.
* Advanced analyst reporting.

---

## 16. Proposed Rollout Phases

### Phase 1: Foundations

* Integrate OpenAlex.
* Build canonical entity resolution.
* Implement retrieval for paper, author, topic, and query.

### Phase 2: Ranking

* Add weighted re-ranking.
* Add explanations for why results surfaced.
* Introduce ranking presets.

### Phase 3: Iterative Research Navigation

* Add traversal breadcrumbs.
* Add mixed-entity result views.
* Improve lab inference and hierarchical topic navigation.

### Phase 4: Quality Improvements

* Tune ranking with user feedback.
* Add more sources.
* Add better summaries and recommended next steps.

---

## 17. Summary

This product will provide **any-to-any research literature retrieval** across papers, authors, labs, topics, and queries. Its core differentiator is a loop that combines **broad retrieval** with **intelligent re-ranking**, enabling users to move through the research landscape from any starting point.

The first implementation should prioritize **OpenAlex** as the data backbone and **LLMs** as the interpretation and intelligence layer.
