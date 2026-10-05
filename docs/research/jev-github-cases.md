[English](jev-github-cases.md) | [한국어](jev-github-cases.ko.md)

# Jev GitHub usage cases and architecture findings

Reviewed 2026-10-05. **Finding:** Jev should receive the task-relevant state with identities, relationships,
constraints, and history intact, and return the contextual decisions needed by code.
One request can contain several typed outputs over that shared state. This is not
a proposal to evaluate DOM elements individually or send a request for every fact.
Aside Jev supports the API, but its browser path uses a line-compressed observation
and an action-only step request, followed by a final semantic audit. The proposal
focuses on preserving context and evaluating a workflow transition as a whole. [Proposed architecture](../rfcs/0001-composable-jev-decisions.md).

## Method and evidence boundaries

GitHub repository searches covered `jev typesafe`, `typesafe-ai`, and the official
`typesafe-ai` organization. Exa requested 30 candidate results across three search
angles: primitive usage, routing/evaluation, and official cookbooks. Discovery
results were deduplicated and then checked against actual source files in eight
GitHub repositories: seven code examples/integrations and one official design guide.
The table is a selected collection, not an exhaustive ecosystem census.

All code links below are pinned to the inspected commits. The
[source manifest](jev-github-sources.json) records repository, revision, exact files,
line ranges, and evidence type. We read source; we did **not** execute these external
projects, call paid APIs, verify production deployments, or reproduce their latency
claims. Official samples, evaluation code, and community integrations are distinct
forms of evidence. Curated `awesome-*` lists, third-party SEO summaries, unrelated
JEV projects, and alternative models advertised as “open Jev” were discovery leads
or exclusions, not proof of TypeSafe usage. Official live docs were also read;
their content is not version-pinned.

## Verified GitHub cases

| Source and evidence type | What the code does | Transfer to Aside Jev |
| :--- | :--- | :--- |
| [TypeSafe Python SDK example](https://github.com/typesafe-ai/typesafe-sdk-python/blob/f078f1e208a0d885154dc758344ae4fce77ac168/README.md#L17-L33) — official sample | Routes a support ticket to a supplied category with an explicit no-match category. | Keep app-owned answer spaces and no-match outcomes; a single Choice is valid when one decision is sufficient. |
| [WorkflowEvals invoice signals](https://github.com/typesafe-ai/WorkflowEvals/blob/0ac3b8ad845429f0d8e064ecfb2430a47c5a25cb/evals/invoice_processing/structured/semantic.py#L46-L75) — official evaluation implementation | Converts question answers into reusable semantic signals; separate code combines exact facts, those signals, and policy profiles. | Separate observation, judgment, and policy; retain signals rather than collapse everything into one action ID. |
| [TypeSafe n8n routing](https://github.com/typesafe-ai/n8n-nodes-typesafe-ai/blob/c12537bbd9ed7159b7bbe23678ca128c7b2fb52b/nodes/TypeSafeAi/TypeSafeAi.node.ts#L98-L150) — official workflow integration | Routes Choice using confidence policy, Noul using true/false boundaries with an uncertainty branch, and Score using ordered levels. | Use policies appropriate to each primitive; do not treat all their numeric fields as the same confidence. |
| [Jev browser question catalog](https://github.com/jkudish/jev-browser/blob/1f0726cc8bc4483b96439504b594a01596d8e347/src/questions.ts#L6-L27) — community browser implementation | Sends action Choice, goal Noul, and stuck Noul over one state; its runtime checks stop conditions before execution. | Bundle independent step judgments and arbitrate before an action. |
| [Pi skill picker](https://github.com/safzanpirani/pi-jev-skill-picker/blob/5a8b300e1adb9b72f53e7cb5952ec8f7e90c758d/extensions/jev.ts#L165-L231) — community skill-selection implementation | Asks a separate Score about each skill, then code applies a floor, sorts results, and selects skills. | This is a skill-ranking use case, not a recommendation to score browser elements individually. Its questions preserve the task context and identify the subject. |
| [Foreman assessment groups](https://github.com/thruwire/foreman/blob/e5d1aa45183382390e388512dcbfebd747ec89ba/src/foreman/foreman/jev.py#L109-L151) — community supervisory implementation | Groups Noul checks by evidence providers and evaluates each group together; responsibilities propose directives for code to select. | Share calls when evidence is shared; separate calls when evidence differs. Keep responsibilities independent of transport. |
| [Neo4jev graph hop](https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L389-L435) — community graph-navigation implementation | Asks next-edge Choice and current-goal Noul together; code applies beam/cutoff budgets. A terminal node can receive Noul without Choice. | Completion is a separate judgment, including on pages without actionable elements. Do not copy graph branching into browser side effects. |

Additional source anchors: WorkflowEvals [policy composition](https://github.com/typesafe-ai/WorkflowEvals/blob/0ac3b8ad845429f0d8e064ecfb2430a47c5a25cb/evals/invoice_processing/structured/decompose.py#L167-L197),
browser [pre-execution gates](https://github.com/jkudish/jev-browser/blob/1f0726cc8bc4483b96439504b594a01596d8e347/src/navigate.ts#L799-L859),
and Foreman [declared limitations](https://github.com/thruwire/foreman/blob/e5d1aa45183382390e388512dcbfebd747ec89ba/README.md#L477-L487).
These are patterns to evaluate, not production performance endorsements.

## Official model semantics

The [official GitHub design guide](https://github.com/typesafe-ai/skills/blob/65a39f393687675ce170e6094757de20370365b9/skills/typesafe-ai/SKILL.md#L95-L148) supports bounded
action selection, so choosing an app-owned action is not inherently misuse.
Its guidance explicitly says atomicity is not limited to literal fact extraction;
a coherent contextual action judgment is valid. Relevant identities and relationships
belong in the state. It distinguishes comparative Choice distributions, yes/no Noul
probabilities, and ordered Score judgments. Questions sharing evidence can be evaluated together;
a question cannot consume another answer from that same request. A dependent
follow-up requires new evidence/state or newly constructed options. Probability,
confidence, permission, and observed truth are different concepts.

The live [System One overview](https://docs.typesafe.ai/concepts/system-one),
[building guide](https://docs.typesafe.ai/concepts/how-to-build-with-system-one),
and [confidence reference](https://docs.typesafe.ai/confidence) reinforce code-owned
control flow and typed judgment composition. They describe a text/JSON input
interface, not direct image/audio/video perception. A faster UI pipeline still
needs a trustworthy browser observation adapter.

## What the current repository actually does

Assessment baseline: `himomohi/aside-jev@969d7b5b93971f6e96fc855fc23731d19a38b2a4`.

| Observed implementation | Architectural consequence / proposed change |
| :--- | :--- |
| [`system_one` supports all three types and up to 32 named questions](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/jev.py#L202-L258). | The capability exists; reusing it is preferable to inventing another API wrapper. |
| [`choose_live` creates only `aside_action`](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/jev.py#L160-L198). | Evaluate the current task/workflow transition against a relational state packet, with the necessary outputs in one call; do not replace it with per-element classification. |
| [`run_browser_flow` receives but discards probabilities and applies one action confidence threshold](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/browser_flow.py#L126-L165). | Retain distributions and distinguish ambiguity, no applicable candidate, and missing evidence. Do not silently weaken the existing execution gate. |
| [`jev_browser_run` performs completion Noul and risk Score after browser completion](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/mcp_server.py#L243-L288). | Evaluate the proposed, already-authorized workflow transition before its effects. Keep a final audit when it judges new post-action evidence; it is not automatically a redundant request. |
| [Final completion Noul and risk confidence use the same configured threshold](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/mcp_server.py#L281-L284). | Calibrate separate policies for answer types and consequences, while preserving the legacy minimum until a replacement is validated. |
| [Observation compaction ranks lines and reports omitted-line counts](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/browser_flow.py#L45-L68); [generic sanitization limits depth and fields](https://github.com/himomohi/aside-jev/blob/969d7b5b93971f6e96fc855fc23731d19a38b2a4/src/aside_jev/aside_bridge.py#L28-L105). | Preserve evidence relationships and declare coverage/missing evidence; omitted lines alone do not establish semantic sufficiency. |

Existing exact-target, stale-page, ON/OFF, authorization, confidence, timeout, and
manual-resumption checks are useful constraints. The evidence supports an
**underused composition capability**, not the assertion that the entire integration
is invalid or that Rust alone fixes semantic architecture.

## Adopt selectively

Adopt coherent task-state packets, one bundled evaluation per semantic checkpoint,
code-owned transitions, and explicit missing evidence. Keep per-primitive policies
and inspect raw outputs. Do not turn the DOM into independent scoring requests;
deterministic checks do not require Jev and should stay in code.
Do not copy another project's numeric thresholds, retries, permissive completion
rules, alternate-action recovery, text-generation providers, or DOM-wide action
space. Those require this application's separate authorization and validation.
No live latency reduction or accuracy improvement is claimed by this research.
