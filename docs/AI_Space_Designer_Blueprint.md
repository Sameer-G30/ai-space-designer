# AI Space Designer — Full Project Blueprint
### A Multimodal, Explainable, Constraint-Aware Space Design & Optimization Platform
*(Critically redesigned from the original 42-section brief, verified against current literature and datasets, September 2026)*

---

## 0. How to read this document

The original brief is ambitious to the point of being **three or four separate PhD-scale research programs stitched together** (real-time SLAM, NeRF/Gaussian Splatting, AR, digital twins, GraphRAG, 12 agents, full 3D pipeline, RL layout optimization, generative image editing with geometric consistency — any ONE of these is a publishable thesis). A 5-person university team building all of it will fail. My job here is to keep the **intellectual core** intact while cutting ruthlessly on scope, and to tell you honestly where the "novelty" claim needs adjusting because *this exact idea already has active 2024–2026 research competing in the same space* (details in §6). That is not bad news — it means the problem is real and fundable-looking, but you must position against these systems rather than pretend they don't exist.

---

## 1. Executive Summary

**AI Space Designer** is a modular pipeline that converts a photographed or measured real-world room into a **structured spatial representation**, parses natural-language user requirements into **structured constraints**, performs **mathematically-grounded multi-objective layout and budget optimization** subject to those constraints, validates the result with a **deterministic + VLM design critic**, generates a **geometry-consistent visualization**, and produces **explanations that are computed from the actual optimization trace rather than invented by an LLM**. It exposes a **Pareto set** of design alternatives (cheap / balanced / premium / sustainable) and supports **counterfactual "what-if" queries** (change budget, room size, occupant count) without a full re-run from scratch where possible.

It is explicitly **not** "LLM + image generator." The generative image model is the *last, cosmetic* step, constrained by geometry computed earlier in the pipeline — not the decision-maker.

---

## 2. Problem Statement

Existing consumer AI interior-design tools (RoomGPT, Spacely AI, Interior AI, ZMO AI, and similar apps) are, based on their own public feature descriptions, fundamentally **diffusion-based image-to-image style transfer tools**: upload a photo, pick a style, get a "redesigned" photo.<br>
What they demonstrably do **not** do:
- Enforce a numeric budget as a hard constraint with a bill of materials
- Guarantee furniture doesn't overlap, block a door, or violate clearance/accessibility rules
- Preserve the *actual* room geometry (walls, windows, doors) between the "before" and "after" image
- Explain *why* a specific object was placed somewhere, grounded in a real decision trace
- Let a user ask "what if I had 50% more budget?" and get a re-optimized (not re-generated-from-scratch) design
- Represent a room as reusable structured data instead of only pixels

Academic research (see §6) has started to attack pieces of this — but almost always for **text-to-scene generation on synthetic datasets** (3D-FRONT, procedurally described rooms), not for **redesigning an actual photographed room with existing furniture the user wants to keep**, under an explicit monetary budget, with retrieval-grounded design knowledge and a faithful explanation layer. That gap is where this project should sit.

---

## 3. Existing System Problems (verified, not assumed)

| System type | What it actually does | What it is missing |
|---|---|---|
| RoomGPT / Interior AI / ZMO AI | Diffusion image restyling from a single photo; style presets<br>*(confirmed via public product descriptions)* | No structured geometry, no budget, no constraint checking, no explanation, no furniture BOM |
| Spacely AI | Rendering/visualization tool for designers and architects (text-to-image, style rendering) | Aimed at professional visualization, not constraint-aware automated design; no optimization layer disclosed |
| Academic text-to-scene systems (Holodeck, LayoutVLM, I-Design, SceneCraft, ATISS) | Generate a *new* furnished 3D scene from a text prompt using LLM/VLM + differentiable or discrete layout solvers, evaluated on 3D-FRONT/MIT-scenes-style benchmarks | Start from nothing or from a floorplan skeleton, not a photographed *existing* room; no monetary budget modeling; no retrieval-grounded design-standard knowledge; limited explanation faithfulness |
| Co-Layout (LLM + grid-based Integer Programming, AAAI 2026) and InteriorAgent (LLM agent + gradient/VLM feedback for constraint satisfaction) | Closely mirror this project's "LLM extracts constraints → optimizer solves geometry → feedback loop fixes violations" idea | Same gap: synthetic/text-driven scene generation, not photo-grounded redesign-with-existing-furniture-and-real-budget |
| HouseLLM | Text-to-floorplan generation (architectural scale, not furniture-level room redesign) | Different granularity (whole-house floorplans, not room interior optimization) |

**Conclusion:** the *combination* you want — CV-perceived real room + must-keep/must-remove existing objects + explicit currency budget + retrieval-grounded standards + faithful explanation + counterfactual interaction + exposed Pareto front — is not something any single system above already ships. That combination, not any individual module, is your defensible novelty.

---

## 4. Proposed System (philosophy)

```
Real Space --> Perceive --> Structure --> Retrieve Knowledge --> Reason/Optimize --> Critique --> Generate --> Explain --> Iterate
```
not
```
Photo --> Prompt --> Image
```

Each arrow is a **separate, independently testable module** with its own inputs/outputs, so failure in one (e.g. depth estimation) degrades gracefully (fallback to manual measurements) instead of breaking the whole system.

---

## 5. Unique Contribution

1. **Photo-grounded, not text-grounded, scene understanding**: the system perceives an actual room (with its actual walls, windows, and furniture the user wants to keep), rather than synthesizing a scene from a text prompt on a synthetic dataset.
2. **Currency-budget-constrained multi-objective optimization** with a real bill-of-materials, not just an abstract "cost" scalar in a paper's ablation table.
3. **Retrieval-grounded constraint sourcing**: ergonomic/accessibility/lighting numbers come from a citable knowledge base, not from LLM memory.
4. **Faithful, computed explanations**: every explanation sentence is templated from actual constraint-satisfaction and sensitivity numbers, with an LLM only doing final-mile fluent phrasing — never inventing the underlying reason.
5. **Counterfactual design as an interaction primitive** ("what if budget +50%", "what if 4 occupants instead of 2") solved as warm-started re-optimization, not full regeneration.
6. **Exposed Pareto frontier** so the user picks a trade-off point instead of receiving one opinionated answer.

---

## 6. Novelty Analysis (evidence-based)

Recent arXiv work (2024–2026) already explores LLM-driven interior layout + optimization:
- *Co-Layout: LLM-driven Co-optimization for Interior Layout* (AAAI 2026) — LLM agents extract structured constraints from text, then grid-based integer programming jointly optimizes room + furniture layout, with coarse-to-fine solving. This is architecturally close to your "Requirement Agent + Layout Optimizer" idea.
- *INTERIORAGENT* — LLM agent for interior-design-aware 3D layout generation, explicitly measuring constraint violations (overlap, clearance, accessibility, visibility) and comparing gradient-based vs. VLM-based feedback loops — this is essentially your "Design Critic" idea, already implemented and benchmarked.
- *HouseLLM* — text-to-floorplan generation at the architectural (whole-house) scale.
- Established prior work: *ATISS* (autoregressive transformer scene synthesis on 3D-FRONT), *LayoutVLM*, *Holodeck*, *I-Design*, *SceneCraft* — all generate indoor scenes from language, several using VLM or LLM agents with geometric constraint solvers.

**What this means for you:** claiming "we are the first to combine LLM reasoning with constraint-aware layout optimization" would not survive peer review — that space is active and crowded as of late 2025/2026. Your genuinely defensible novelty is narrower and more concrete:
> *A system that perceives an actual physical room from photos/video (not a text prompt or synthetic dataset), preserves user-specified existing furniture, optimizes layout **and** a real monetary budget jointly, grounds constraints in a retrieval knowledge base, and produces explanations that are provably derived from the optimizer's own decision trace rather than free-generated by an LLM — exposed to the user as an interactive, counterfactual-capable Pareto frontier rather than a single output.*

Cite Co-Layout, InteriorAgent, HouseLLM, ATISS, Holodeck, LayoutVLM explicitly in your related-work section — using them to sharpen your contribution, not ignoring them.

---

## 7. Complete Architecture (redesigned)

The original diagram is reasonable in spirit but overcomplicated (separate Video/Camera/Floorplan top-level branches, 12 downstream agents, a strictly linear critic-then-generate order). Redesign:

```
                         INPUT LAYER
        Photo(s) | Video | Floorplan scan | Manual measurements | Text requirement
                              │
                    ┌─────────▼─────────┐
                    │ PERCEPTION MODULE  │  (CV: detection, segmentation, depth, room type)
                    └─────────┬─────────┘
                              │
                 ┌────────────▼────────────┐
                 │ STRUCTURED SCENE GRAPH  │  (single source of truth — JSON/graph, versioned)
                 └────────────┬────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
REQUIREMENT PARSER     RAG KNOWLEDGE LAYER     (existing objects, dims, openings — already in graph)
 (NL -> structured        (ergonomics, access-
  constraints JSON)        ibility, pricing, style
        │                  compatibility, dataset-  
        │                  derived priors)          
        └────────────┬────────────┬───────────────┘
                      ▼            
              DESIGN ORCHESTRATOR (lightweight controller, not an agent itself)
                      │
   ┌──────────────────┼───────────────────┐
   ▼                  ▼                   ▼
LAYOUT+FURNITURE   STYLE & MATERIAL    BUDGET & SUSTAINABILITY
OPTIMIZER (MIP/CP  RECOMMENDER (embed- SCORER (linear constraints
+ local search)    ding similarity +    folded into the same
                    RAG-grounded rules) optimizer objective)
   └──────────────────┼───────────────────┘
                      ▼
             CANDIDATE DESIGN SET (Pareto front, 4-8 points)
                      ▼
             DETERMINISTIC CONSTRAINT CHECKER  (hard gates: overlap, clearance, budget, must-keep)
                      ▼
             VLM DESIGN CRITIC (soft checks: style coherence, visual plausibility) — optional second pass
                      ▼
        ┌─────────────┴─────────────┐
        ▼                           ▼
GEOMETRY-CONDITIONED           EXPLANATION GENERATOR
IMAGE/3D GENERATION            (templated from optimizer trace,
(ControlNet-style,             LLM only for fluent phrasing)
depth/seg conditioned)
        └─────────────┬─────────────┘
                      ▼
              USER INTERFACE (compare, select, iterate, ask "what if")
                      │
                      └──────────────→ back to Orchestrator (warm-started re-optimization)
```

Key changes vs. the original:
- **One structured scene graph is the single source of truth**, not a separate "structured space model" plus later ad-hoc state.
- **The optimizer produces a Pareto *set*, not a single design**, before the critic and generator ever run — this avoids redundant generate→critique→regenerate cycles for designs the user wouldn't have picked anyway.
- **The Orchestrator is a controller, not an "agent"** in the LLM-autonomous sense — most of its logic is a deterministic state machine (see §10 for why this matters).
- **Video/camera/floorplan are input adapters that all normalize into the same scene graph**, not separate top-level pipeline branches.

---

## 8. AI Pipeline (component-by-component strategy)

| Stage | Approach | Train / pretrained / rule-based? |
|---|---|---|
| Room-type classification | Fine-tune a small pretrained ViT/CLIP-based classifier on Places365-style indoor subset + your custom labels | Fine-tune |
| Object detection | Pretrained open-vocabulary detector (e.g. Grounding DINO / YOLO-World) fine-tuned on furniture-heavy subset | Fine-tune |
| Segmentation | Pretrained SAM2 (prompted by detection boxes) | Pretrained, no training needed |
| Depth / room geometry | Pretrained monocular depth model (e.g. Depth Anything-family) + simple plane-fitting for walls/floor | Pretrained + rule-based geometry fitting |
| Requirement parsing (NL → JSON) | Instruction-tuned LLM with structured-output (function-calling / JSON schema) constrained decoding | LLM API or small local model, prompt-engineered, not fine-tuned initially |
| Layout optimization | Mixed-Integer Programming / Constraint Programming solver (OR-Tools) | Deterministic optimization, no training |
| Furniture recommendation scoring | Weighted scoring function + embedding similarity (CLIP-style) for style match | Rule-based + pretrained embeddings |
| RAG retrieval | Pretrained sentence-embedding model + vector DB | Pretrained |
| Design critic (hard checks) | Deterministic geometry code (collision, clearance) | Rule-based, no ML |
| Design critic (soft checks) | VLM API call on rendered image | Pretrained API model |
| Visualization | Pretrained diffusion model + ControlNet-style conditioning (depth/segmentation maps from the scene graph) | Pretrained, possibly LoRA fine-tune for style consistency |
| Explanation | Template engine over optimizer trace + LLM for fluent rewriting | Rule-based core + LLM API for phrasing only |

**Minimize training.** The only components worth actually fine-tuning with your limited compute/dataset are: (1) room-type + furniture-class detection on your labeled indoor subset, and (2) optionally a LoRA on the diffusion model for consistent "redesign" style. Everything else should be pretrained-off-the-shelf or purely algorithmic. This maximizes research bandwidth to spend on the **optimization + explanation + evaluation** contributions, which is where the actual novelty lives.

---

## 9. Computer Vision Pipeline

Recommended, justified choice per task — avoid "because it's popular":

- **Scene/room classification**: a lightweight pretrained image classifier fine-tuned on indoor scene categories. No need for a foundation VLM here; overkill for a 15–30-class problem.
- **Object detection**: an open-vocabulary detector (Grounding DINO-class or YOLO-World-class) so you are not locked to a fixed furniture taxonomy — you can add "gaming chair" or "3D printer" without retraining. Fine-tune on a furniture-focused subset for precision.
- **Segmentation**: SAM2 prompted by detection boxes is sufficient and requires **no training** — do not build a custom segmentation network; that would be pure overengineering for this project's actual research question.
- **Depth estimation**: a modern monocular depth model gives *relative* depth reliably; **do not** promise metric-accurate room dimensions from a single RGB photo — this is a known hard, unreliable problem. Instead:
  - If the user supplies **one photo**: estimate relative depth + object proportions, explicitly flag dimension estimates as **low-confidence** and ask for one manual measurement (e.g. wall length) to re-scale everything. This uncertainty-flagging is itself a nice, honest research point (§7 in the brief specifically asked for this — keep it, it's good).
  - If the user supplies **a short walkthrough video**: use classical Structure-from-Motion (COLMAP) or a lightweight visual-odometry pipeline to get a metric-scaled sparse point cloud, which resolves the depth ambiguity far better than single-image depth. This is realistically implementable by one CV-focused team member using existing COLMAP tooling, **not** a from-scratch SLAM system.
  - **NeRF / Gaussian Splatting**: not justified for the MVP or even the advanced version. They solve *novel-view rendering quality*, which is not this project's bottleneck (you need structured geometry + a nice final visualization, not free-viewpoint photorealistic rendering). Mark this explicitly as "future/experimental," not a core pipeline component. Recommend against spending team-months on it.
- **Floor plan parsing** (if a 2D floor plan image is uploaded instead of a photo): a segmentation/detection model trained/fine-tuned on **CubiCasa5K** (see §19) is the right tool — this is a genuinely different, well-scoped sub-task from photo-based room understanding, worth its own small model.

---

## 10. Multi-Image / Video Understanding

Recommended pipeline for video input, using battle-tested classical tools rather than research-grade neural SLAM:

```
Video → uniform + motion-based frame sampling → COLMAP (SfM) → sparse point cloud + camera poses
      → depth model refined by sparse points → plane fitting (walls/floor/ceiling)
      → object detection per keyframe → 3D bounding-box lifting via triangulation across frames
      → merged structured scene graph with explicit confidence scores per dimension
```

- **SLAM / real-time visual odometry**: not needed — you don't require real-time tracking, only an offline reconstruction from a short walkthrough clip. COLMAP (offline SfM) is simpler, better documented, and sufficient.
- **RGB-D input** (if the team has access to a phone with LiDAR, e.g. recent iPhones): a very strong "cheat code" — if available, use it, since it gives metric depth directly and skips most of the above complexity. Recommend building the input adapter to accept RGB-D optionally.
- Represent uncertainty explicitly: every dimension in the scene graph should carry a `confidence` field (e.g. `"high"` from RGB-D/manual measurement, `"medium"` from multi-view SfM, `"low"` from single-image monocular depth), and downstream optimization should be conservative (add safety margins) when confidence is low.

---

## 11. Structured Space Representation

Recommendation: **a typed JSON scene graph, stored in PostgreSQL with a `jsonb` column, not a full graph database.**

Reasoning:
- A **knowledge graph / Neo4j** is justified for the *design-knowledge RAG* (ergonomic rules, style-compatibility, standards) where multi-hop relational queries ("what lighting fits a study+gaming room per accessibility guideline X") are genuinely graph-shaped.
- The **per-room scene representation**, however, is a shallow tree (room → walls/openings → objects, each with attributes) — this is exactly what `jsonb` + a couple of indexed columns handles well, with far less operational overhead than standing up a graph database for a structure that's 2–3 levels deep.
- Use **GLTF** as the interchange/export format once you build the 3D visualization, since it's the de-facto standard for web 3D (Three.js loads it natively) and has actual furniture-asset ecosystems (Objaverse assets are largely GLTF/OBJ-convertible).
- Skip BIM/USD/IFC formats — genuinely useful for AEC-industry interoperability, but a large added complexity for zero benefit to a university research prototype; note as future work if the team wants to target professional architects later.

Example schema (kept from the brief, lightly extended with confidence and versioning):

```json
{
  "scene_id": "room_0091",
  "version": 3,
  "room_type": "gaming_room",
  "dimensions": {"length": 4.5, "width": 3.8, "height": 2.8, "confidence": "medium"},
  "openings": [{"type": "window", "wall": "north", "position": 2.1, "width": 1.2}],
  "objects": [
    {"id": "obj_01", "type": "desk", "position": [2.1, 1.2], "rotation": 0,
     "dimensions": [1.4, 0.7, 0.75], "movable": true, "must_keep": false, "confidence": "high"}
  ]
}
```

---

## 12. Requirement Understanding

Use an **instruction-tuned LLM with constrained/structured JSON-schema output** (function-calling style), not a custom-trained NER model — the requirement space is too open-ended and low-volume for training-from-scratch to pay off, and modern LLMs are reliably good at schema-constrained extraction when given a clear schema and a few examples (few-shot prompting). Validate the output against a JSON schema server-side and re-prompt on failure. A smaller local model can be substituted later for cost/latency once you've collected enough real examples to build a fine-tuning set — treat that as a stretch goal, not MVP.

---

## 13. RAG System

Recommendation: **hybrid dense+keyword retrieval over a vector database (pgvector, since you already have PostgreSQL), with metadata filtering — skip GraphRAG for the MVP.**

- **GraphRAG genuinely helps** when questions require multi-hop reasoning across explicitly relational facts (e.g., "which materials are compatible with X style AND meet Y sustainability certification AND fit under Z price") — this *can* occur in your design-knowledge layer, so it's a legitimate **advanced-version** feature, not a must-have.
- For MVP, straightforward RAG (embed a chunked knowledge base of ergonomic guidelines, accessibility clearances, furniture catalog specs, material properties → retrieve top-k relevant chunks → feed into the requirement/critic/explanation modules as grounding context) captures most of the value at a fraction of the engineering cost.
- **Multimodal RAG** (retrieving reference images of "dark modern gaming room" alongside text) is a nice, cheap add-on for the Style Agent and worth including — embed furniture catalog images with the same embedding model family used for text where possible (or a separate CLIP-style image embedding index), no extra infra needed beyond a second pgvector table.
- Reranking: a lightweight cross-encoder reranker over the top-20 retrieved chunks is worth the modest engineering cost and measurably improves grounding quality in RAG literature broadly.

---

## 14. Agent Architecture — Consolidated

**Twelve agents is overengineering** for a 5-person team and, more importantly, for the actual computation being done. Several of the proposed "agents" (Budget Agent, Sustainability Agent, Accessibility Agent) are not autonomous reasoning entities — they're **constraint terms and objective-function weights inside one optimizer.** Turning each into a separate LLM-driven "agent" that has to coordinate via natural language adds latency, cost, and failure surface for zero benefit, since these are numeric constraints, not judgment calls.

**Recommended: 5 functional modules, only 2 of which are actually LLM/VLM "agents":**

1. **Perception Module** (deterministic CV pipeline — not an agent)
2. **Requirement Agent** (LLM — the one genuine "understand messy human language" task)
3. **Layout & Recommendation Optimizer** (deterministic optimization + scoring functions folding in budget, sustainability, accessibility, ergonomics, style-match as constraints/weighted objective terms — not agents, math)
4. **Design Critic** (deterministic hard-constraint checker + one VLM call for soft/aesthetic judgment — a "critic agent" in the loose sense, but mostly rule-based)
5. **Explanation Agent** (LLM, but constrained to rephrase a computed trace — the second genuine LLM-agent role)

This keeps the "agentic AI" framing (which is a fine thing to say in your report — you do have LLM-driven components making tool calls and iterating) while being honest that most of the system's intelligence is **optimization and retrieval, not autonomous agent negotiation.** This is also easier to evaluate, debug, and write a clean ablation study on (§28).

---

## 15. Layout Optimization — Mathematics

**Recommended method: Constraint Programming / Mixed-Integer Programming for the discrete placement problem, with a genetic algorithm or local search as a fallback/refinement for the continuous multi-objective trade-off, producing a Pareto set.**

Why, ranked against alternatives:
- **Reinforcement learning**: attractive on paper, but needs a large amount of simulated layout episodes and careful reward shaping to converge — a large time sink with real risk of not converging well within a university project's timeline, for a problem that classical optimization solves more reliably. Recommend against as a primary method; fine as a *future work* discussion.
- **Pure differentiable optimization** (as used in INTERIORAGENT's gradient-based feedback): effective for continuous position/rotation refinement once a discrete layout skeleton exists, but not a full solution on its own because many constraints (does this fit against this wall segment, is a door blocked) are naturally discrete/combinatorial.
- **Genetic Algorithms / Particle Swarm / Simulated Annealing**: reasonable and easy to implement, good at exploring multiple candidate solutions for the Pareto set, but weaker at guaranteeing hard constraints (no overlap, budget ≤ limit) are exactly satisfied — better used as a *second stage* to refine/diversify solutions already found feasible by CP/MIP.
- **Bayesian Optimization**: good for the furniture *selection* scoring weights or hyperparameter tuning, not the geometric placement problem itself (too few, expensive-to-evaluate iterations needed vs. its strength in low-dimensional expensive black-box settings).

**Recommended two-stage design:**
1. **Stage 1 (feasibility, MIP/CP with OR-Tools' CP-SAT)**: discretize the room into a grid (as Co-Layout does with a "Modulor"-inspired grid — a good, verified precedent), solve for a feasible non-overlapping placement satisfying hard constraints (clearance, door access, must-keep positions, budget upper bound on selected furniture set).
2. **Stage 2 (multi-objective refinement, weighted-sum + NSGA-II-style genetic search or simple grid-search over weight vectors)**: starting from Stage-1-feasible solutions, generate a Pareto front across (functionality, aesthetics, cost, sustainability) by varying objective weights, producing the 4–8 candidate designs the user chooses between.

Objective (kept close to the brief, with weights user-adjustable at query time):

$$ S(D) = w_1 L(D) + w_2 C(D) + w_3 E(D) + w_4 B(D) + w_5 A(D) + w_6 Sus(D) $$

where each term is normalized to [0,1]: L = layout/space-utilization efficiency, C = circulation-area adequacy, E = ergonomic-guideline satisfaction (retrieved from RAG), B = budget compliance (1 if ≤ budget, penalized smoothly if over), A = style/aesthetic compatibility (embedding similarity to requested style), Sus = sustainability score (material/certification lookup).

Hard constraints (must always hold, enforced in Stage 1, not just penalized):
- No furniture-furniture overlap
- Door/window clearance ≥ code minimum
- All `must_have` items present, all `must_keep` items retained at feasible positions
- Total cost ≤ budget (unless user explicitly asks for over-budget "premium" option)
- Minimum circulation width maintained
- Accessibility clearance (wheelchair turning radius etc., when requested)

---

## 16. Design Critic

Two-tier, as in the redesigned architecture:
1. **Deterministic geometric/rule checker** (collision, clearance, budget, must-keep, accessibility) — this must be authoritative for anything safety- or constraint-critical. A VLM should never be the sole gate on "does this door still open."
2. **VLM soft critic** (given the rendered visualization + the structured design) — for aesthetic coherence, style consistency, "does this look plausible/uncanny," which is genuinely hard to encode as hard rules. Treat its output as an advisory score/flag, not a blocking gate, and log disagreement rate with the deterministic checker as an evaluation metric (this is a nice concrete research measurement: *how often does the VLM flag issues the geometric checker misses, and vice versa*).

---

## 17. Generative AI Pipeline (Visualization)

Recommendation: **image-to-image diffusion editing with structural conditioning (depth map + segmentation map derived directly from the optimized scene graph), not free-form text-to-image.**

To prevent hallucinated geometry (the brief's stated concern, correctly):
- Render a **depth map and semantic segmentation map from the optimized 3D scene graph itself** (not from the model's imagination) and feed those as ControlNet-style conditioning alongside the original photo's wall/window/door regions held fixed (inpainting mask covers only the *changed* furniture regions).
- Never regenerate the whole image freely; **inpaint only the regions that the optimizer actually changed**, keeping walls/windows/doors pixel-locked from the original photo wherever the optimizer didn't move them.
- Add an automated **post-generation consistency check**: re-run the object detector on the generated image and diff against the intended scene graph (right furniture count/type/rough position) — flag and regenerate if mismatched. This closes the loop the brief worried about and is a legitimate evaluation metric (§29, "geometry consistency").
- For 3D output, a simpler and more reliable path than photorealistic generative 3D is: place actual (or matched) **GLTF furniture assets** (from Objaverse or a curated furniture-asset subset) into a Three.js scene at the optimizer's exact coordinates — this guarantees geometric correctness by construction, and is far less failure-prone than trying to make a generative image model respect exact coordinates.

---

## 18. 3D Pipeline

Recommended stack: **Three.js / React Three Fiber, web-deployed, GLTF assets.**
- Best fit for: web deployment (no install), team already likely doing a React frontend, large ecosystem, and a clear future path to WebXR for AR (§20) without switching engines.
- **Blender**: use only as an **offline authoring/pre-processing tool** (e.g., converting/optimizing downloaded 3D-FUTURE/Objaverse furniture assets into clean lightweight GLTFs), not as a runtime component.
- **Unity/Unreal**: unnecessary overengineering for this project's scope — much heavier toolchains, worse web-deployment story, no meaningful rendering-quality benefit for a furniture-placement visualization use case.
- **Gaussian Splatting**: nice for *displaying the original captured room* photorealistically if you did multi-view capture (§10), but not for the *redesigned* room (you need discrete, editable, constraint-respecting objects, which splats are bad at). Mark as an optional "advanced" way to visualize the *before* state only.

---

## 19. AR

**Future scope, not MVP or advanced.** Justification: AR (ARCore/ARKit/WebXR) needs real-time camera-plane tracking robust enough to place furniture correctly in physical space — a substantial engineering project on its own, disjoint from this project's core optimization/explainability research contribution. Including it in the "Advanced" tier risks the team spending its final month debugging plane-detection instead of finishing the evaluation/paper. If a team member has spare bandwidth at the very end, a WebXR proof-of-concept that simply places the *already-computed* GLTF layout into AR view (no new AI, pure rendering) is a safe, demo-friendly stretch goal.

---

## 20. Furniture Recommendation

Score function (kept from the brief, made concrete):

$$ Score(item) = w_1\,\text{StyleSim}(item, style) + w_2\,\text{FitBudget}(price) + w_3\,\text{FitsSpace}(dims, slot) + w_4\,\text{FunctionMatch} + w_5\,\text{Rating} + w_6\,\text{Sustainability} $$

- `StyleSim`: cosine similarity between an image/text embedding of the item and the requested style description (CLIP-family embeddings — pretrained, no training needed).
- `FitsSpace`: hard/soft check against the exact free wall-segment/floor-area the optimizer allocated to that slot.
- Build a **furniture catalog** (custom-scraped or synthetic, with price/dimensions/material/style tags) as your recommendation corpus — see §22–23 for how a 5-person team can realistically build this without infringing on retailer data terms (prefer open catalogs, or a small manually-curated set of a few hundred realistic items with plausible attributes, clearly disclosed as a research prototype catalog, not real live pricing).

---

## 21. Budget Optimization

Fold budget directly into the Stage-1 MIP as a linear constraint (`Σ price_i · x_i ≤ Budget`), and expose it as one axis of the Pareto front (§15) rather than a separate "agent." Present the BOM (bill of materials) as a normal itemized table generated directly from the selected design — no ML needed here at all, pure deterministic aggregation.

---

## 22. Explainable AI Framework

**Hard rule: the LLM may only rephrase facts that already exist in the optimizer's decision trace. It must never be asked to "explain why" without being given the actual numbers/constraints that drove the decision.**

Concretely:
1. Log every constraint check and every objective-term contribution during optimization (which constraints were active/binding, which alternative was rejected and why — e.g., "table B rejected: 12cm over remaining wall segment").
2. Compute simple **sensitivity scores** by construction: since Stage 1/2 already explores multiple candidate designs and weight vectors, you get local sensitivity almost for free — e.g., re-solving with `budget + 10%` (already needed for the counterfactual feature, §23) directly gives you `ΔScore/ΔBudget` without extra machinery.
3. Feed only these concrete facts (binding constraints, rejected alternatives, sensitivity deltas, retrieved RAG justification snippet) into a short LLM prompt whose only job is fluent English phrasing — never asking it to reason about *why*, only to *phrase* the already-computed why.
4. Evaluate explanation **faithfulness** by round-tripping: parse the LLM's generated explanation back for factual claims (e.g., "budget," "clearance," a specific number) and check them against the actual trace — flag any unsupported claim. This is a genuinely useful, fundable evaluation contribution (§29).

This replaces the brief's "SHAP / counterfactual explanations / causal reasoning" grab-bag with the concrete parts that actually apply here: SHAP-style feature attribution doesn't map cleanly onto a discrete/combinatorial optimizer's decisions, but **sensitivity analysis via re-optimization** does, and it's already something your architecture computes as a side effect of the counterfactual feature. Keep that; drop SHAP as it doesn't fit a non-differentiable, combinatorial pipeline.

---

## 23. Counterfactual Design

Because Stage 2 already produces a family of solutions across weight vectors, a counterfactual query ("budget +50%," "4 occupants instead of 2") is just: **update the relevant constraint/parameter, warm-start Stage 1 from the previous feasible solution (fixing unaffected furniture positions where still valid), and re-solve.** This is both a genuine UX differentiator and a computationally cheap operation if implemented as incremental re-optimization rather than a from-scratch pipeline run — worth explicitly measuring re-optimization latency vs. full-pipeline latency as an evaluation number.

---

## 24. Digital Twin Possibility

Feasible **at prototype scope** as: the persisted, versioned structured scene graph (§11) *is* a lightweight digital twin — every design version, cost, and constraint state is already tracked there. Framing it explicitly as a "digital twin" in your report is reasonable and low-cost, since you're not adding new engineering beyond what §11 and §25 (versioning) already require — just don't overpromise real-time sensor integration, which is genuinely out of scope.

---

## 25. Design Versioning

Straightforward append-only version table (`scene_id`, `version`, `parent_version`, `diff`, `score`, `timestamp`) in PostgreSQL. Compute and display diffs (furniture added/removed/moved, cost delta, score delta) between any two versions — cheap, high perceived value, good demo material.

---

## 26. Multi-Objective Optimization — Pareto Exposure

This is one of your strongest, cheapest-to-build differentiators (§15 already produces it as a natural byproduct of Stage 2). UI: show 4–8 named points on a 2D projection (e.g., cost vs. aesthetic score, with functionality/sustainability as secondary filters or a toggle), letting the user pick "cheapest / balanced / premium / most sustainable" — exactly as the brief envisioned, and it costs nothing extra beyond what the optimizer already computes.

---

## 27. Knowledge Graph — Where It Actually Helps

Use a lightweight graph layer (could even be relational tables modeling `Furniture -[COMPATIBLE_WITH]-> Style`, `Style -[REQUIRES]-> Material`, etc., rather than standing up Neo4j) **only for the design-knowledge base** (§13), not for per-room scene state (§11). If the team has bandwidth and wants a genuine GraphRAG advanced feature, Neo4j + a graph-aware retriever is justified there specifically — evaluate this as an "Advanced," not MVP, feature; measure whether it actually improves retrieval quality over plain vector RAG before committing more engineering to it (this is a good, honest ablation, see §28).

---

## 28. Datasets — Verified

| Dataset | Purpose | Size (verified) | License (verified) | Project use |
|---|---|---|---|---|
| **CubiCasa5K** | Floor plan parsing (rooms, walls, doors, windows, 80+ icon categories, polygon annotations) | 5,000 floor plans (4,200/400/400 train/val/test split), from ~15,000 Finnish real-estate source images | **CC BY-NC 4.0** (non-commercial) | Fine-tune/validate the floor-plan-upload input adapter |
| **3D-FRONT** | Professionally-designed synthetic furnished room layouts | ~6,800 houses, ~14,000–19,000 furnished rooms depending on filtering, paired with **3D-FUTURE** (~7,300–13,000 textured furniture objects, ~43 categories) | Free for academic/research use (registration required) | Pretraining/validation prior for layout plausibility scoring, style-compatibility training data, furniture asset source |
| **Structured3D** | Photorealistic synthetic indoor scenes with rich 3D structure annotations | ~3,500 house designs (professionally designed) | Free for academic use (registration) | Depth/plane/geometry model validation |
| **NYU Depth V2 / SUN RGB-D** | Real RGB-D indoor scenes, depth + semantic segmentation ground truth | NYU-D2: ~1,449 densely labeled + ~400K raw frames; SUN RGB-D: ~10,000 RGB-D images | Academic research use | Validate/benchmark depth-estimation and segmentation accuracy on real (not synthetic) rooms |
| **Objaverse / Objaverse-XL** | Large-scale 3D object assets, including furniture | Objaverse: ~800K objects; Objaverse-XL: ~10M objects | ODC-By / mixed per-source licenses — check per-asset attribution requirements before redistribution | Source of GLTF furniture assets for the 3D visualization pipeline |
| **FurniScene** | Denser furnished-room dataset addressing 3D-FRONT's sparse small-object coverage | ~112K rooms, ~40K objects, 89 categories | Check current release terms (recent, 2024 paper) | Optional supplement if 3D-FRONT's furniture diversity proves insufficient |

**Action item for the team**: before using any of these in a submitted paper or public demo, re-verify current license terms directly on the dataset's official page at time of use — these change, and CubiCasa5K's **non-commercial** clause in particular matters if you ever want to commercialize beyond the university project.

---

## 29. Custom Dataset Design

A 5-person team cannot hand-annotate thousands of real rooms. Realistic plan:
1. **Procedural/synthetic generation** (majority of volume): programmatically sample room dimensions + furniture sets + requirement templates + budgets, and run your *own* optimizer to generate the paired `(input, structured requirement, candidate designs, scores, explanation)` records — this doubles as your evaluation/regression test suite and your RAG-grounding validation set, and requires no manual labeling since your own optimizer generates the ground truth from known rules.
2. **Small real-photo set** (order of 100–300 rooms): department members' own rooms/labs/offices, with manual measurement as ground truth for geometry evaluation — small but real, used to validate the CV pipeline's actual accuracy (not the synthetic pipeline, which would trivially validate itself).
3. **Human/expert validation on a subset**: have a few designs rated by people with genuine interior-design or architecture familiarity (even a couple of guest reviewers) for the human-evaluation metrics in §29 of the evaluation section — you do not need dozens of professional designers, but "no human ever looked at this" is a real weakness reviewers will flag.

---

## 30. Dataset Pipeline

The brief's proposed folder structure is fine; keep it, with one addition — separate `synthetic/` from `real/` explicitly under `raw/` and `processed/`, since you'll want to report metrics on each separately (this is scientifically important: a system that only works on synthetic data is a much weaker claim than one validated on real photos too).

```
datasets/
├── raw/{synthetic, real}/
├── interim/
├── processed/
├── annotations/
└── metadata/
```

---

## 31. Model Strategy Summary

| Category | Components |
|---|---|
| Pretrained, used as-is | SAM2 (segmentation), depth model, CLIP-family embeddings, sentence embeddings for RAG |
| Fine-tuned | Object detector (furniture classes), room-type classifier, optionally a diffusion LoRA for style consistency |
| Rule-based / deterministic | Geometry/constraint checker, BOM aggregation, versioning/diffing, sensitivity computation |
| Optimization algorithm | CP-SAT (OR-Tools) for Stage 1, weighted-sum/NSGA-II-style search for Stage 2 Pareto front |
| LLM/VLM API | Requirement parsing, explanation phrasing, VLM soft critic |
| Explicitly not building | Custom SLAM, NeRF, Gaussian Splatting, from-scratch segmentation network, RL layout policy, 12-agent negotiation framework |

---

## 32. Evaluation Metrics

- **CV**: mAP/IoU for detection, segmentation IoU, depth error (where ground truth available from the real-photo subset), room-dimension error (cm) vs. manually measured ground truth.
- **Layout**: hard-constraint violation rate (should be ~0% by construction from Stage 1 — report it anyway as a sanity check), circulation-area adequacy, room-utilization ratio, requirement-satisfaction rate (fraction of `must_have`/`must_keep` items present).
- **Budget**: cost-estimation error vs. a manually priced ground-truth BOM on a sample, budget-violation rate (should be 0 by construction — report as validation).
- **Generation**: CLIP-similarity (style match), SSIM/perceptual similarity for unchanged regions (walls/windows should be near-identical pre/post), and your own **geometry-consistency check** (§17) as a novel metric: fraction of generated images where re-detected furniture matches the intended scene graph.
- **Recommendation**: Precision@K / Recall@K / NDCG against a held-out set of "acceptable" items per query (from your synthetic generation ground truth or human ratings).
- **Explanation faithfulness**: fraction of explanation claims that round-trip-verify against the optimizer trace (§22) — a genuinely novel, cheap-to-compute metric for your paper.
- **Human evaluation**: pairwise preference (system vs. RoomGPT-style baseline vs. ablated variants) on a small panel, standard practice in this literature (used by Co-Layout, INTERIORAGENT, and others above) — replicate their protocol for comparability.

---

## 33. Ablation Study

Directly follow the brief's proposed ladder, since it maps cleanly onto your 5 consolidated modules:
1. LLM (requirement parsing) + diffusion image generation only *(≈ commercial-app baseline)*
2. + CV-perceived real structured scene (vs. assumed/text-described room)
3. + RAG-grounded constraints
4. + CP/MIP optimization (vs. LLM free-form layout guessing)
5. + Design Critic feedback loop
6. Full system (+ explanation faithfulness layer + Pareto exposure + counterfactual)

Measure at each stage: constraint-violation rate, budget compliance, requirement satisfaction, human preference score. This ladder **is** your core empirical contribution and paper's main results table.

---

## 34. Baselines

Real, verifiable baseline categories to compare against (not hypothetical):
- **Commercial style-transfer apps**: RoomGPT, Interior AI, Spacely AI — as the "image generator only" baseline class.
- **Academic layout-generation systems**: ATISS, Holodeck, LayoutVLM, I-Design, SceneCraft — as the "LLM/VLM + scene synthesis, no real-photo grounding" baseline class.
- **Academic constraint-optimization systems**: Co-Layout, INTERIORAGENT — as the closest architectural relatives; be explicit in your report about what you add beyond them (real-photo input + budget + RAG + faithful explanation + Pareto/counterfactual UX).

Do not claim capabilities like "RAG: rare in existing systems" or "Explainability: rare" without citing the above — some of them do include feedback/critic loops (INTERIORAGENT explicitly does). Be precise: your differentiation is *photo-grounded redesign with a real budget and faithful explanations*, not "we invented agentic layout optimization."

---

## 35. Research Questions (refined)

- **RQ1**: How accurately can a monocular-photo + optional short video pipeline recover metrically-usable room geometry (dimensions, object positions) compared to manual measurement ground truth, and how should uncertainty be communicated to downstream optimization?
- **RQ2**: Does explicit constraint-programming-based layout optimization produce measurably fewer functional/spatial violations than an LLM asked to directly propose furniture coordinates (replicating and extending the comparison already reported by Co-Layout/INTERIORAGENT, but on real-photo-derived rooms rather than text-described ones)?
- **RQ3**: Does retrieval-grounding of ergonomic/accessibility/style constraints measurably change design quality or requirement-satisfaction compared to relying on an LLM's parametric knowledge alone?
- **RQ4**: Does a deterministic-plus-VLM design-critic loop reduce constraint violations and improve human-rated design quality, and where do the deterministic and VLM checkers disagree?
- **RQ5**: Can LLM-generated design explanations be made *provably faithful* to the optimizer's actual decision trace, and how often does unconstrained LLM explanation (no trace access) hallucinate reasons compared to trace-grounded explanation?
- **RQ6**: How does exposing a full cost-vs-quality Pareto frontier (vs. a single "best" design) affect user-reported decision confidence and satisfaction?
- **RQ7**: Can counterfactual re-optimization (warm-started from a prior solution) match full-reoptimization design quality at meaningfully lower latency, enabling real-time "what-if" interaction?

---

## 36. Expected Contributions

1. An end-to-end pipeline connecting real-photo room perception to constraint-programming-based, budget-aware, multi-objective layout optimization — a combination not present as a single system in the reviewed literature.
2. A trace-faithful explanation methodology for combinatorial design optimization (a generalizable idea beyond interior design).
3. An empirical ablation quantifying the marginal value of RAG grounding, optimization vs. free-form LLM layout, and critic feedback — directly extending the comparison style used in Co-Layout/INTERIORAGENT to a photo-grounded setting.
4. A small but real-world-validated dataset (§29) pairing real room photos with manual ground-truth measurements, useful beyond this project for benchmarking monocular room-geometry estimation.

---

## 37. Technology Stack (revised)

| Layer | Recommendation | Notes |
|---|---|---|
| Frontend | React / Next.js, TypeScript, Tailwind, React Three Fiber | matches team's likely existing skills, good WebXR future path |
| Backend | FastAPI (Python) for AI services; a single service is enough — avoid needless microservice split for a 5-person team | Node.js layer only if the frontend team strongly prefers it for the non-AI CRUD parts |
| AI/ML | PyTorch, Hugging Face Transformers, OR-Tools (CP-SAT), a diffusion library (Diffusers) | |
| Database | PostgreSQL + pgvector (scene graphs, requirements, RAG embeddings, versioning) | one database engine, less operational overhead than adding Neo4j/Redis for MVP |
| Object storage | S3-compatible bucket for images/renders | |
| Advanced-only additions | Neo4j (only if GraphRAG ablation shows real value), Redis (only if latency profiling shows caching is actually needed) | don't pre-add infra you haven't proven you need |
| Deployment | Docker Compose for the team's own dev/demo; a single cloud GPU instance for model serving | Kubernetes is overengineering at this scale |

---

## 38. Database Design (sketch)

- `scenes` (scene_id, version, room_type, dimensions jsonb, openings jsonb, objects jsonb, confidence jsonb, created_at)
- `requirements` (requirement_id, scene_id, raw_text, structured jsonb)
- `designs` (design_id, scene_id, requirement_id, weights jsonb, score float, cost float, objects jsonb, parent_design_id)
- `furniture_catalog` (item_id, category, dims, price, style_tags, material, embedding vector)
- `rag_chunks` (chunk_id, source, text, embedding vector, metadata jsonb)
- `explanations` (design_id, claim_text, supporting_trace_ref, verified boolean)

---

## 39. API Architecture

REST/JSON over FastAPI, roughly:
- `POST /scenes` (upload photo/video/floorplan → returns structured scene graph + confidence)
- `POST /requirements` (NL text → structured requirement JSON)
- `POST /designs/optimize` (scene_id + requirement_id + optional weight preferences → Pareto set of design_ids)
- `POST /designs/{id}/counterfactual` (parameter delta → re-optimized design_id, warm-started)
- `POST /designs/{id}/visualize` (→ generated image/3D scene)
- `GET /designs/{id}/explanation`
- `GET /designs/{id}/versions` (version history/diff)

---

## 40. Security & Privacy

- Treat uploaded room photos as sensitive personal data by default (they reveal home layout, belongings, sometimes faces/documents in frame).
- Run **face/PII blurring as an automatic pre-processing step** before any image is stored or sent to a third-party API — this is cheap (a face-detection pass) and meaningfully reduces risk.
- **Cloud processing with the third-party model APIs (LLM/VLM/diffusion) is realistically required** for this project's scope — a university team cannot host frontier-scale VLM/diffusion models locally and get good quality. Be transparent with users that images are sent to external APIs for processing, offer a deletion policy (delete raw images after N days, keep only the derived structured scene graph, which is far less sensitive), and strip EXIF/GPS metadata on upload.
- Standard API hygiene: authenticated endpoints, rate limiting, encrypted storage at rest and in transit.

---

## 41. 5-Member Team Responsibilities (revised for the consolidated architecture)

| Member | Modules | Datasets | Key deliverable | Research angle |
|---|---|---|---|---|
| **M1 — Perception & Geometry (CV lead)** | Object detection fine-tuning, segmentation integration, depth/geometry, COLMAP video pipeline, floor-plan parser | CubiCasa5K, NYU-D2/SUN RGB-D, custom real-photo set | Scene-graph generator from photo/video/floorplan with confidence scores | RQ1 |
| **M2 — Optimization & Recommendation** | CP-SAT layout solver, Pareto-front generation, furniture scoring/recommendation, budget/BOM | 3D-FRONT/3D-FUTURE for layout priors, custom furniture catalog | Optimizer service producing candidate design set | RQ2, RQ6, RQ7 |
| **M3 — Requirement, RAG & Explanation** | LLM requirement parser, RAG knowledge base + retrieval, explanation template engine + faithfulness checker | Curated design-standard corpus (ergonomics, accessibility, style guides) | Requirement→JSON pipeline, RAG service, explanation generator | RQ3, RQ5 |
| **M4 — Generation, Critic & 3D** | Diffusion+ControlNet visualization, geometry-consistency checker, deterministic + VLM critic, Three.js 3D scene | Objaverse/3D-FUTURE assets | Visualization pipeline + critic loop | RQ4 |
| **M5 — Frontend, Backend, Data & Evaluation** | API layer, database, frontend UI (comparison, versioning, Pareto picker, what-if), synthetic dataset generation, evaluation harness | Custom synthetic dataset (§29) | End-to-end app + evaluation dashboard + ablation runner | Cross-cutting: owns §33 ablation infrastructure |

Every member's module reads/writes the **shared scene-graph/design schema** (§11, §38) — this is the integration contract that prevents the "five isolated modules that don't talk to each other" failure mode the brief worried about.

---

## 42. Development Roadmap

- **Phase 0** (2 wks): finalize schema (scene graph, requirement JSON, design record), API contracts between all 5 members.
- **Phase 1** (3 wks): dataset acquisition/licensing check, synthetic dataset generator v1.
- **Phase 2** (4 wks): perception pipeline (detection, segmentation, depth) on single photos; floor-plan parser.
- **Phase 3** (2 wks): scene-graph assembly + confidence scoring.
- **Phase 4** (3 wks): requirement parser + RAG knowledge base v1.
- **Phase 5** (4 wks): CP-SAT layout optimizer (Stage 1) + budget constraint.
- **Phase 6** (2 wks): furniture recommendation scoring.
- **Phase 7** (2 wks): Pareto front generation (Stage 2).
- **Phase 8** (3 wks): deterministic + VLM design critic.
- **Phase 9** (3 wks): geometry-conditioned visualization + consistency checker.
- **Phase 10** (2 wks): trace-faithful explanation generator.
- **Phase 11** (3 wks): video/multi-image pipeline (COLMAP), 3D Three.js viewer — **advanced tier, can slip without blocking MVP demo**.
- **Phase 12** (ongoing, parallel from Phase 4): frontend integration.
- **Phase 13** (3 wks): full evaluation + ablation study.
- **Phase 14** (3 wks): paper writing.

Total ≈ 8–9 months, realistic for a university team working part-time alongside coursework; compress by starting Phase 12 (frontend) in parallel from early on rather than at the end.

---

## 43. MVP / Advanced / Future

**MVP** (must work for the demo/defense):
Single photo → perception → structured scene graph (with confidence) → NL requirement → RAG-grounded requirement JSON → CP-SAT layout optimization with budget constraint → 2–4 point Pareto set → deterministic constraint checker → geometry-conditioned image visualization → BOM → trace-faithful explanation.

**Advanced** (if time permits):
Multi-image/video via COLMAP → richer 3D scene (Three.js, real furniture assets) → VLM soft critic → GraphRAG comparison ablation → counterfactual re-optimization → design versioning/diffing UI.

**Future / explicitly out of scope for this project**:
Real-time camera/AR, true digital-twin sensor integration, Gaussian Splatting/NeRF rendering, RL-based layout policy, large-scale live product-catalog integration, multi-user real-time collaborative editing.

---

## 44. Risks and Limitations

- **Single-photo metric geometry is unreliable** — mitigate by requiring at least one manual measurement or a short video for anything beyond rough layout suggestions; be upfront about this limitation in the paper rather than overclaiming accuracy.
- **RAG knowledge base quality bottleneck** — a small, hand-curated design-standards corpus is easy to build shallowly but hard to build *well*; budget real time for this, it's not "just embed some PDFs."
- **Diffusion generation drift** (regenerated image doesn't match intended layout) — mitigated by the inpainting-only + consistency-check approach in §17, but expect this to be an ongoing tuning problem, not a solved-once module.
- **Licensing**: CubiCasa5K is non-commercial only; furniture-catalog data must not be scraped from live retailer sites without checking terms of service — use synthetic/curated catalog data for anything beyond internal research use.
- **Scope creep** is the single biggest risk given the original brief's size — the MVP/Advanced/Future split in §43 exists specifically to protect against this; revisit it explicitly at each phase gate.

---

## 45. Compute Requirements

- Fine-tuning a detector/classifier on a few thousand images: feasible on a single consumer/lab GPU (e.g., one RTX 3090/4090-class card or a modest cloud GPU instance) over a few days.
- Diffusion inference + occasional LoRA fine-tuning: a single mid-range cloud GPU instance, used on-demand rather than always-on, keeps cost manageable for a student budget.
- LLM/VLM calls: budget for API costs (requirement parsing + explanation phrasing + soft critic calls) — these are cheap per-call but add up during heavy dataset generation (§29's synthetic pipeline will make many calls; consider a smaller/local model for that bulk-generation step and reserve the frontier API model for interactive user-facing calls).
- CP-SAT solving: CPU-only, fast (seconds) for room-scale problems — no special hardware needed.

---

## 46. Research Paper Structure

Introduction (motivate photo-grounded, budget-aware redesign gap) → Related Work (explicitly: RoomGPT-class apps, ATISS/Holodeck/LayoutVLM/I-Design/SceneCraft, Co-Layout, INTERIORAGENT, HouseLLM) → System Overview → Perception & Structured Representation → Optimization Formulation → RAG Grounding → Design Critic → Explanation Faithfulness Methodology → Experimental Setup (datasets, baselines) → Results (ablation ladder, Pareto quality, geometry-consistency, explanation faithfulness, human evaluation) → Limitations → Conclusion.

---

## 47. Final Recommended Project Title

> **"PhotoSpace: Photo-Grounded, Budget-Constrained Multi-Objective Optimization for Explainable Interior Redesign"**

(Alternative, if the department prefers a broader-sounding title: *"AI Space Designer: A Constraint-Aware, Retrieval-Grounded System for Explainable Real-Space Redesign Optimization"* — but the first title is more precise about the actual novel contribution and will read better to reviewers familiar with the Co-Layout/INTERIORAGENT line of work.)

---

## 48. Final Recommended Architecture (one line)

**Perception (CV) → Structured Scene Graph → RAG-grounded Requirement Parsing → CP-SAT + Pareto Multi-Objective Optimization (budget as hard constraint) → Deterministic + VLM Critic → Geometry-Conditioned Inpainting Visualization → Trace-Faithful Explanation → Versioned, Counterfactual-Capable Iteration Loop.**

---

## 49. Technologies to REMOVE

- NeRF / Gaussian Splatting as core pipeline components (keep only as an optional "before" visualization footnote, if at all)
- Custom from-scratch SLAM
- Reinforcement learning for layout (use CP/MIP + genetic refinement instead)
- Separate "12-agent" LLM negotiation framework (consolidate to 5 modules, §14)
- Neo4j/GraphRAG for per-room scene state (keep JSON in Postgres; Neo4j only justified for the design-knowledge layer, and only if ablation shows it beats plain vector RAG)
- Unity/Unreal for 3D (Three.js is sufficient and web-native)
- BIM/USD/IFC interoperability (out of scope; GLTF is enough)
- AR as an MVP/Advanced feature (push to Future)
- SHAP-style attribution for the optimizer's decisions (doesn't map onto a combinatorial solver — use re-optimization-based sensitivity instead, which you get for free)

## 50. Technologies to ADD (genuine differentiation)

- Explicit **confidence/uncertainty fields** on every geometric estimate, propagated into conservative optimization margins
- **CP-SAT (OR-Tools)** as the core layout solver — free, mature, well-documented, exactly suited to this constraint structure
- **Inpainting-only + post-generation consistency re-detection** for the visualization step, closing the geometry-hallucination loop
- **Trace-faithful explanation with automated claim verification** — a concrete, novel, cheap-to-implement evaluation contribution
- **Warm-started counterfactual re-optimization** as a first-class, low-latency interaction mode
- **Exposed Pareto frontier UI** as the default output format, not a single "best" design
