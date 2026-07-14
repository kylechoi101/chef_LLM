# chef_LLM — Design Document

**Date:** 2026-07-05
**Status:** Draft for review (brainstorming phase — no implementation yet)
**Author:** Kyle Choi, with Claude

---

## 1. Vision

Images, sound, and video have been digitized; taste has not. This project's hypothesis is that taste already has a serialization format humans invented centuries ago: **the recipe**. Recipes exist because a dish tasted good and people wanted to reproduce that taste — exactly why source code exists for behavior.

- Recipe = source code
- Cooking = execution
- The dish = runtime artifact
- Taste = observable output behavior

**Goal:** train a chef LLM that *generates* genuinely new, executable, delicious recipes — generative, not retrieval. The system treats the world's recipe corpus the way coding-agent pipelines treat GitHub: extract, normalize to an intermediate representation, score for quality, train, and evaluate against benchmarks.

**Program-level success criterion:** blinded human panels cannot reliably distinguish model-generated recipes from professional test-kitchen recipes, while generated recipes stay measurably novel (above a plagiarism floor in ratio/technique space) and pass a food-safety suite at 100%.

---

## 2. The core insight: the missing oracle

The recipe↔code analogy holds almost everywhere, but breaks in exactly one load-bearing place, and that break dictates the entire architecture:

> **Code has a cheap, fast, objective oracle — compile it, run the tests. Taste does not.** A recipe's test suite is a human mouth: slow (hours per evaluation), expensive (ingredients + labor), subjective (palates differ), and noisy (skill and equipment vary).

Therefore the central engineering problem is not the model or the data cleaning — it is **building a layered proxy oracle (a verifier stack)** and designing every upstream stage to feed it. A secondary break: execution is nondeterministic (same recipe, different kitchen → different dish), which makes **robustness across cooks** a first-class quality dimension with its own signals and benchmarks.

### 2.1 The mapping

| Code concept | Recipe equivalent |
|---|---|
| Source code | Recipe text (ingredients + procedure) |
| Compiler + hardware | Cook + kitchen (nondeterministic) |
| Compile error | Unexecutable recipe (ingredient used but never listed = undefined variable) |
| Runtime bug | Cooks fine, tastes bad |
| Unit tests / CI | Reviews, ratings, test-kitchen iteration |
| Issue tracker + patches | Review text with modifications ("too salty — I halved the soy sauce") |
| Forks / version history | Recipe variants; dish genealogy trees |
| Language spec | Food science (McGee, flavor chemistry) |
| Type system | Ingredient functional roles (salt/fat/acid/heat, binder, leavening, aromatic) |
| Algorithm vs. parameters | **Ratios** vs. absolute quantities (recipes are scale-invariant) |
| "Works on my machine" | Recipe fails outside the author's kitchen/skill level |
| Security vulnerability | Food-safety hazard (undercooked poultry, botulism risk) |

Two structural consequences:

1. **Ratios are the canonical representation.** Bread is 5:3 flour:water at any scale (Ruhlman's *Ratio*). Two textually different recipes with the same ratio vector and technique graph are the same program, differently formatted. This drives deduplication, novelty measurement, and generation.
2. **Recipes are lossy serializations of an embodied program.** Taste-critical control flow lives in sensory feedback loops ("until it smells nutty," "until the dough windowpanes") that assume the cook is a trained sensor array. The IR must represent termination conditions as sensory predicates, not just times — and the ceiling of a text-only model is bounded by this serialization loss (motivating eventual image/video grounding).

---

## 3. System architecture

```
 Sources (tiered)          ETL                    Corpus views              Training                 Evaluation
┌──────────────────┐  ┌──────────────┐  ┌──────────────────────────┐  ┌──────────────────┐  ┌─────────────────────┐
│ T0 test kitchens │  │ Parse → IR   │  │ IR + text + pairs        │  │ Continued        │  │ L1 lint metrics     │
│ T1 review sites  │→ │ Normalize    │→ │ (IR↔text, parent↔variant │→ │  pretraining     │→ │ Constraint pass@k   │
│ T2 bulk scrapes  │  │ Lint + safety│  │  diffs, review→fix)      │  │ SFT (gen/edit/   │  │ Repair bench        │
│ Science/QA/DBs   │  │ Enrich       │  │ Quality + provenance tags│  │  repair/critique)│  │ Frozen critic score │
└──────────────────┘  │ Dedup+geneal.│  └──────────────────────────┘  │ Verify-and-select│  │ Novelty frontier    │
                      └──────────────┘                                │  loops (L1/L2/L3)│  │ CookEval (human)    │
                                                                      └──────────────────┘  │ Safety suite (100%) │
                                                                                            └─────────────────────┘
```

---

## 4. ETL pipeline

### 4.1 Extract — tiered sources, each with a distinct role

| Tier | Sources | Role | Notes |
|---|---|---|---|
| **T0** — tested canon | America's Test Kitchen, Serious Eats, NYT Cooking, professional books (Escoffier, *The Professional Chef*, Modernist Cuisine) | Highest-trust exemplars ("code with CI from expert maintainers") | Low volume; licensing required for some |
| **T1** — community + reviews | Food.com (230k recipes + 1.1M interactions, open on Kaggle), Allrecipes, Epicurious | The review corpora — the issue tracker, test reports, and patch history | **Reviews are the crown jewel**, not the recipes |
| **T2** — bulk long tail | Recipe1M+ (1M recipes + images), RecipeNLG (2.2M), OpenRecipes | Pretraining volume | Heavy filtering; expect massive near-duplication |
| **Substrate** — non-recipe | Cooking StackExchange (debugging corpus with accepted answers), food-science texts (McGee et al.), FlavorDB / FooDB compound databases, USDA FoodData Central, YouTube transcripts | Language spec, symbol tables, tacit knowledge | FlavorDB + USDA map ingredient tokens → chemical/physical properties |

Extraction is half-done for much of the web: schema.org/Recipe JSON-LD ships structured `recipeIngredient`, `recipeInstructions`, `aggregateRating`, `review`, times, and yield.

### 4.2 Transform — compile to an intermediate representation

**Stage 1 — Parse to IR.** Ingredients become `(quantity, unit, canonical_ingredient_id, prep_state)`. Instructions become a **dataflow DAG**: nodes are operations `(action, params, termination_condition)`; edges carry intermediate products. Termination conditions are first-class and typed: time-based (`9 min`), sensory (`until golden and nutty-smelling`), or both (`8–10 min, until golden`). Recipe flow-graph extraction is an established NLP task (Yamakata et al.) — reuse prior art.

Illustrative IR sketch (schema, not implementation):

```json
{
  "id": "...", "title": "...", "yield": {"qty": 4, "unit": "serving"},
  "provenance": {"tier": "T1", "source": "food.com", "rating": {"mean": 4.6, "n": 2143}},
  "ingredients": [
    {"iid": "ing:onion_yellow", "qty_g": 300, "prep": "sliced thin", "roles": ["aromatic", "sweetness_source"]}
  ],
  "graph": [
    {"op": "saute", "inputs": ["ing:onion_yellow", "ing:butter"],
     "params": {"heat": "medium-low"},
     "until": {"time_min": [35, 45], "sensory": "deep brown, jammy"},
     "out": "node:caramelized_onions"}
  ],
  "ratios": {"basis": "total_mass", "vector": {"...": 0.0}},
  "annotations": {"flavor_compounds": "...", "nutrition": "...", "safety_flags": [], "lint": {"pass": true}}
}
```

**Stage 2 — Normalize.**
- Ingredient entity resolution (scallions = green onions = spring onions) against a canonical ontology.
- Unit → mass conversion via per-ingredient density tables (1 cup flour ≈ 120 g; 1 cup sugar ≈ 200 g — volume units are ingredient-dependent).
- Reduce to **ratio space** (generalized baker's percentages). Absolute quantities are retained as one parameterization.

**Stage 3 — Lint (static analysis).**
- *Referential integrity:* no ingredients used-but-unlisted or listed-but-unused (a large fraction of scraped recipes fail this alone).
- *Quantity sanity:* outlier detection per ingredient class (4 cups of salt is a bug).
- *Physical plausibility:* rule bank from food chemistry — leavening/acid balance, emulsion limits, temperature/time coherence, known antipatterns ("caramelize onions in 5 minutes," "boil at 300°F").
- *Safety pass (hard gate):* poultry/pork internal temperatures, raw flour/egg handling, garlic-in-oil botulism, canning acidity, allergen labeling. Used both as a corpus filter and later as a generation gate. Non-negotiable.

**Stage 4 — Enrich (type annotations).**
- Flavor-compound vectors per ingredient (FlavorDB/FooDB).
- Nutrition per ingredient and computed per serving (USDA).
- **Contextual functional role:** the same ingredient plays different types in different steps (butter = cooking fat in a sauté, emulsifier in a pan sauce). Role assignment is per-node, not per-ingredient.
- Derived metrics: critical-path time, parallelism, technique set, equipment requirements, skill estimate.

**Stage 5 — Dedup + genealogy.**
- Near-duplicate detection in **ratio + technique-DAG space, not text space** (SEO plagiarism defeats text dedup; AST-equivalent hashing does not).
- Collapse true duplicates; **keep variants** and cluster them into dish families with canonical centers.
- Outputs: cluster size = popularity prior (a dish with 10,000 variants encodes centuries of cultural hill-climbing); distance-from-centers = the novelty metric used at generation time.

**Stage 6 — Decontaminate** against the benchmark suite (held-out dishes, StackExchange items, sabotage seeds), or generative evals silently become memorization tests.

### 4.3 Load — corpus views

Emit multiple aligned views per recipe, tagged with provenance tier, quality score, and cuisine so training can condition on quality:

1. Structured IR (teaches structure and enables verification).
2. Natural-language text (teaches fluency).
3. IR ↔ text translation pairs (parse and pretty-print, both directions).
4. **(parent → variant) diffs** from genealogy clusters (teaches directed editing).
5. **(recipe → review complaint → reviewer's fix)** triples (teaches debugging; reviews contain literal patches).
6. (recipe → outcome metadata): ratings, reproduction evidence, failure reports.

---

## 5. Quality model — what makes a recipe "good"

"Good" is multi-axis. The three intuitive signals (chef vs. home, ratings, similar existence) measure **different things** and must not be collapsed into one score:

| Axis | What it measures | Signal | Caveats |
|---|---|---|---|
| **Executability** | Does it compile | Lint pass rate | Cheapest, most objective; run first |
| **Robustness** | Works on other machines | Review *variance*, "followed exactly, perfect" vs. "needed 20 more minutes", reproduction count | The strongest home-corpus virtue |
| **Authority** | Who maintains it | Provenance tier (test-kitchen CI vs. blog) | Chef ≠ better for home context: pro recipes often assume pro hardware/skill (portability problem). Chef sources teach the technique ceiling; home corpora teach the robustness floor. Keep both, tagged. |
| **Hedonic success** | Is it delicious | Bayesian-shrunk ratings (IMDb-style: 4.6×2,000 ≫ 5.0×3), retention language ("I've made this weekly for years"), saves/remakes | Per-platform inflation; survivorship bias (abandoners don't review) |
| **Novelty / redundancy** | Relationship to the existing corpus | Distance in ratio+DAG space from dish-family centers | Dedup signal for the corpus; popularity prior (cluster size); novelty axis at generation time |

**Implementation approach:** weak supervision — treat each signal as a noisy labeling function (Snorkel-style) and train a single quality classifier, as done for "textbook-quality" code/pretraining filters (phi-1, FineWeb-Edu). The classifier does double duty: corpus filtering and seeding the reward model.

**Mine the diffs.** Review text such as "cut the sugar in half" is a patch with an outcome attached — the closest thing this domain has to a failing test pointing at a line. These (recipe, complaint, fix, outcome) tuples are disproportionately valuable and justify prioritizing review-rich sources.

---

## 6. Training plan

Do **not** pretrain from scratch: the full corpus is ~10⁹–10¹⁰ tokens and general world knowledge (chemistry, geography, culture) improves recipes. Start from a strong general LLM.

**Architecture decision (2026-07-13):** the generator is an **LLM** — recipes are discrete, symbolic, compositional (language-shaped), and constrained decoding into the Thermomix step grammar yields executability by construction. JEPA-style models serve as the **critic**, not the generator: decoding latents back into executable recipes is a hard problem the LLM already solves (see L2 below).

**Data-mix decision (2026-07-13):** breadth vs. depth is a training-mix question, not a scraping constraint. Scrape everything; collapse only near-identical copies, never variants. **Breadth** (many dishes) → continued pretraining: teaches the technique vocabulary and composition manifold. **Depth** (variant/tweak diffs per dish) → SFT/preference data: the scarce, high-value signal that teaches ∂taste/∂recipe — which edits preserve or improve a dish. Same split code models use (pretrain on all repos, fine-tune on commits/PRs). Thermomix sources hand over the split directly: Cookidoo official = curated breadth; Rezeptwelt variants + comment tweaks = depth.

1. **Continued pretraining** — full enriched corpus in dual format (text + IR, with translation pairs), food-science substrate, Cooking StackExchange.
2. **SFT on the high-quality slice**, with deliberate task diversity:
   - *Generate:* constraints → recipe (pantry lists, dietary limits, cuisine briefs, fusion briefs).
   - *Edit:* make it vegan; halve sodium; scale 4 → 50 servings (nonlinear — spices and pan surface area don't scale with mass; a genuine reasoning test).
   - *Repair:* broken recipe + symptom → diagnosis + fix (from the StackExchange corpus).
   - *Critique:* predict what reviews will complain about.
   - *Explain:* why this step order — grounded in the science substrate.
3. **Verifier stack** (the core engineering investment):
   - **L1 — Linter:** deterministic ETL checks. Free; catches compile errors; safety gate.
   - **L2 — Learned critics:** (a) *taste critic* reward model trained on ratings + review outcomes; (b) feasibility simulators for the computable chemistry — baking, emulsions, gels, leavening have usable equations; heat transfer is modelable. Baking is the most unit-testable domain in cooking.
     *Instantiation (decided 2026-07-13): JEPA-style, non-generative.* Encoder over recipe IR trained with a latent predictive objective (mask a step / ingredient / ratio block; predict its embedding from context), plus an energy head: low energy for real high-rated recipes, high for corrupted ones. Negatives are not just cheap but **controllable** — the §7 mutation operators (drop the acid, 10× the salt, emulsify after the boil) manufacture hard negatives with known failure modes. Trap: a critic trained only on synthetic corruptions learns to detect corruption artifacts, not bad taste — mix negative sources (mutations + low-rated real recipes + review-diff "before" versions + early-generator samples) and refresh them as the generator improves. Side benefit: the critic's embedding space is a better novelty metric than raw ratio space.
   - **L3 — Humans:** test kitchen + crowdsourced home cooks (heterogeneous-hardware CI; measures robustness directly). Allocated by active learning to generations where L2 is uncertain or stakes are high.
4. **Generate → verify → select → retrain loops** (rejection sampling / self-taught; more stable than pure policy-gradient RL here), with:
   - KL leash to the SFT policy (stay on the edible manifold),
   - explicit novelty bonus (distance from dish-family centers),
   - hard safety constraints (L1 gate, never traded off),
   - scheduled re-anchoring of the critic with fresh L3 human data.

### 6.1 Training compute spec — the ideal machine (added 2026-07-13)

**Sizing logic.** Corpus is ~10⁹–10¹⁰ tokens; base model is a 7–14B open-weights LLM. Continued pretraining of an 8B model on 10¹⁰ tokens ≈ 6·N·D ≈ 5×10²⁰ FLOPs ≈ **~2 days on one 8×H100 node** at realistic MFU (14B: ~3–4 days). Conclusion: this is a **single-node project**. Rent, don't buy — a run costs ~$1k at ~$2/GPU-hr; an owned node costs $250k+.

**The asymmetry that shapes the spec:** this project is *inference-heavy, not training-heavy*. The generate→verify→select loops and per-checkpoint benchmarks (§7 #1–#5) consume more GPU-hours than the training runs. Optimize for serving throughput (vLLM-class batching), not multi-node interconnect.

| Tier | Hardware | What runs on it | Cost |
|---|---|---|---|
| **0 — Dev (UCSD DataHub, decided 2026-07-13)** | DataHub pod: 10 GB RAM, 100 GB persistent storage, remote | ETL — CPU-bound and fully streamable in 10 GB RAM (MinHash signatures for 2M recipes ≈ 1 GB); 100 GB storage fits all v1 *text* corpora (RecipeNLG ~2.3 GB, Food.com <1 GB, Recipe1M+ text ~1.5 GB). **Recipe1M+ images (200 GB+) do not fit — v1 is text-only**, images deferred to Phase 4 | **$0** |
| **1 — Workhorse (DSMLP student partition first, rented node as fallback)** | Observed on the cluster (2026-07-13): **n33 = 7×H100 at 0/7 used, 192 CPU, 1.5 TB RAM, student partition**; 2×4 L40S free; 16× 24 GB-class (b24gb), A30s, A5000s mostly idle. its-ai H100 nodes are saturated | Critic training (any free 24 GB GPU, hours). CPT: 8B on 10¹⁰ tokens ≈ 48 h on 7×H100, ≈ 3.5 days on 4. Fair-share/GPU-per-user caps and preemption apply — multi-GPU multi-day holds need instructor/research approval and batch (`kubectl`) jobs with checkpointing | **$0 if approved**; else rented 8×H100 ≈ $1k/run |
| **2 — Only-if** | 4–8 nodes + InfiniBand (ACCESS site or rented) | 70B-class model or Phase 4 multimodal — not before | Defer |

**Run strategy (decided 2026-07-13): pilot before spending.** First CPT run = 8B on ~10⁹ tokens (highest-quality slice) on 4×H100 ≈ **8 hours — an overnight batch job, free on n33**. Measure benchmarks §7 #1–#4 against the base model before committing to the full 10¹⁰-token run; domain adaptation often saturates well before max tokens, so the pilot may reveal the full run is unnecessary.

**Escalation and fallbacks:** (1) DSMLP n33 with approval — free; (2) ACCESS allocation (Kyle: eligibility unconfirmed, to verify) — SDSC Expanse GPUs are aging V100s, but ACCESS also brokers NCSA Delta/DeltaAI and PSC Bridges-2 (A100/H100-class); (3) rent (~$1k/run, no permission needed). **Local machine scope:** a strong personal computer (incl. high-memory Apple Silicon) is viable for ETL dev, constrained-decoding work, inference, and even LoRA-SFT of 7–8B on the ~10⁸-token SFT slice (~1–2 days) — but **not CPT**: at ~10¹³–10¹⁴ effective FLOPS the 10¹⁰-token run takes months-to-a-year vs. 2 days on the H100 node.

Free-tier constraints: (a) acceptable-use — frame as course/research-affiliated (also unlocks the approval for multi-GPU holds); (b) pods idle-cull — batch scripts with checkpoints to the persistent volume, never long-lived notebooks; (c) no scraping from campus infrastructure — moot for v1, all sources are bulk downloads.

**Per-phase budget (maps to §10):** Phase 0 ≈ $0 GPU (parsing/dedup are CPU; one brief embedding pass for clustering). Phase 1 ≈ $500 (critic is ≤1B params — hours, not days). Phase 2 ≈ $5–15k (3–10 CPT/SFT runs incl. ablations). Phase 3 ≈ $2–5k (inference-dominated). **Total v1 program: ~$10–30k rented compute.**

**Base-model requirements (non-negotiable):**
- Open weights, license permitting derivative training (Llama/Qwen/Mistral class).
- **Strong multilingual** — the Thermomix corpora are German/Spanish/Italian/French-heavy (Rezeptwelt is German-dominant). An English-only base wastes the best data.
- Long context NOT required: recipes are 1–2k tokens. Train at 4–8k context — a meaningful memory/compute saving; don't pay for 128k.

**Stack (boring on purpose):** PyTorch + HF/torchtune, FlashAttention, FSDP only if >14B; vLLM with grammar-constrained decoding (xgrammar/outlines) for the generation loops — needed anyway to emit valid TM-step programs; W&B for tracking. Corpus is 10–100 GB class: local NVMe + object storage, no exotic dataloading. Reproducibility mirrors §11 A: pinned seeds, versioned data mixtures, logged configs — the training-side equivalent of pinned firmware. The food-domain version of reward hacking: a ratings-trained critic learns that fat + sugar + salt scores well, and an unconstrained policy converges to butter-bacon-sugar everything. Guardrails: diversity constraints, nutrition constraints, novelty bonus, and a strict separation between the *training* reward model and a *frozen evaluation* critic.

**Phase 2 (out of scope for v1): multimodal grounding.** Because recipes are lossy serializations of embodied programs, images of target states (Recipe1M+ pairs recipes with photos) and technique video lift the ceiling — e.g., doneness classifiers grounding "until golden." Deferred, but the IR's sensory termination predicates are designed to accept this grounding later.

---

## 7. Benchmark suite

Tiered by cost, mirroring the verifier stack. Automatic tiers run every checkpoint; human tiers run quarterly.

| # | Benchmark | Analog | Method | Cost |
|---|---|---|---|---|
| 1 | **Compile rate** | Syntax validity | % of generations passing the linter | Free |
| 2 | **Constraint satisfaction, pass@k** | HumanEval | Briefs with machine-checkable constraints ("these 5 ingredients, ≤30 min, vegan, <600 kcal/serving"); verify by parsing output | Free |
| 3 | **Repair bench** | SWE-bench | Held-out StackExchange failures (judge vs. accepted answers) + **synthetically sabotaged recipes** (remove the acid, wrong leavening, bad temp — mutation testing; detection/repair auto-checkable) | Cheap |
| 4 | **Frozen-critic hedonic score** | Reward-model eval | Calibration first: critic must rank held-out *real* recipes by true rating (Spearman); only then does its score on generations mean anything | Cheap |
| 5 | **Novelty–quality frontier** | Diversity/creativity evals | Distance-to-nearest-training-cluster vs. predicted quality; frontier area + cross-prompt diversity (mode-collapse check: 100 briefs ≠ 100 braised chickens) | Cheap |
| 6 | **CookEval** | Arena / human eval | Quarterly blinded bake-offs: (a) win rate vs. matched test-kitchen recipes; (b) *spec adherence* via descriptive sensory panels — did it deliver the promised "bright and herbaceous"? (borrow food-science methodology: 9-point hedonic scale, triangle tests); (c) reproduction variance across ≥3 cooks of different skill | Expensive |
| 7 | **Safety suite** | Security evals | Prompts that tempt unsafe output (medium-rare chicken, reused raw-poultry marinade, low-acid canning, silent allergen swaps). **100% required.** | Cheap |

Goodhart protections: the evaluation critic (#4) is frozen and disjoint from the training reward model; CookEval (#6) periodically re-calibrates it; benchmark items are decontaminated from training data (§4.2 stage 6).

---

## 8. Prior art (the thesis has receipts)

- **Ahn et al. 2011, flavor-pairing network:** shared-compound pairing predicts Western pairings and is *inverted* in East Asian cuisine → pairing priors must be learned per-cuisine, never hardcoded.
- **IBM Chef Watson (2014):** compound-overlap novelty generation; proved the creativity half and demonstrated the predicted gap — no verifier stack, weak procedures.
- **NotCo "Giuseppe":** commercial generative food formulation (plant-based analogs) — the generative approach ships as a business.
- **Gastrograph AI:** commercial consumer-preference prediction — a working taste reward model exists today.
- **Flavor houses (Givaudan, Firmenich):** taste is already digitized at the molecule level industrially; recipes are the consumer-scale encoding.
- **Datasets/NLP:** Recipe1M+, RecipeNLG, Food.com/Kaggle interactions, recipe flow-graph corpora (Yamakata et al.).
- **Electronic tongues/noses:** exist but narrow (beverage QC) — a someday hardware-in-the-loop CI, not load-bearing now.

---

## 9. Open decisions

Each carries a recommendation; none is finalized.

1. **Beachhead domain — RESOLVED (2026-07-13): Thermomix.** Supersedes the cocktails/baking recommendation. Rationale: the device is a standardized VM (same hardware, firmware, heating curves for every user), which eliminates the "works on my machine" break — reviews measure the recipe, not the cook. Guided-cooking steps are already bytecode over a small closed instruction set (speed / temp / time / reverse / mode), so the IR collapses into the device API, the compile-rate benchmark becomes literal validation against the step grammar and physical limits (bowl volume, temperature caps), and constrained decoding gives executability by construction. Known ceiling: weak searing/Maillard, no oven — the reachable taste manifold is soups, sauces, doughs, steamed dishes, desserts. Acceptable; that is what a beachhead is. Incumbent AI (Cookidoo recommendation/search) is retrieval over a catalog — a different layer than verified generative synthesis; the portable asset is the method (IR + verifier stack + benchmarks), and the device is the lab rig, not the moat. Corpus-contamination corollary: post-2023 community sources need an AI-slop provenance filter; the official catalog is human-tested.
2. **Objective weighting.** Novel-but-familiar weeknight cooking (robustness-weighted) vs. avant-garde creativity (novelty-weighted). Changes the reward mix and which benchmark is primary. Recommendation: robustness-weighted v1; creativity as a conditioning knob, not the default.
3. **Data rights strategy.** The review corpora are the moat. Food.com's dump is open; NYT/ATK are licensed. Recommendation: build v1 entirely on open data (Food.com, RecipeNLG, Recipe1M+, StackExchange, USDA, FlavorDB) and treat licensed T0 as an upgrade path. Thermomix specifics: Cookidoo (official catalog) is paywalled/licensed — check ToS before scraping; Rezeptwelt (community platform) is public and variant-rich.
4. **Physical ground-truth budget.** Even ~50 actually-cooked recipes with structured tasting notes materially calibrates the critic. Recommendation: plan it as a real line item from the start, not an afterthought — and include the instrumented eval rig (§11 B, retrofit version) so every cooked recipe also yields a process trace, not just a tasting note.

---

## 10. Phasing

- **Phase 0 — Corpus + linter (beachhead = Thermomix):** ETL for Cookidoo/Rezeptwelt-style recipes; IR = the device step grammar; normalization, lint (including device physical limits), dedup/genealogy. Deliverable: a clean, quality-scored, ratio-space corpus and lint metrics on it.
- **Phase 1 — Critics:** quality classifier (weak supervision), taste critic v0, feasibility rules. Critic v0 is the JEPA-style encoder + energy head (§6 L2) — it needs no generator, which is why it precedes Phase 2. Deliverable: calibrated critic (Spearman on held-out ratings).
- **Phase 2 — Generative model:** continued pretraining + SFT; benchmarks #1–#5 running per checkpoint.
- **Phase 3 — The loop:** generate→verify→select→retrain; first small CookEval; safety suite gating all releases.
- **Phase 4 — Scale-out:** expand domains beyond the beachhead; licensed T0 data; multimodal grounding; hardware upgrade path per §11.

Each phase becomes its own implementation plan when reached; this document is the umbrella spec.

---

## 11. Ideal cooking-machine spec (target execution platform; training compute is §6.1)

Thermomix is the available approximation; this is what the architecture actually wants. Three roles fall out of the system design: the machine is a **deterministic executor** (the VM), an **instrument** (the profiler/debugger), and a **closed-loop runtime** (control flow). Use this as a scorecard for platform choices and partnerships — and as the gap analysis against the beachhead device.

### A. Deterministic execution — the VM

| Capability | Spec | Serves | Thermomix today |
|---|---|---|---|
| Closed-loop temp control | ±1°C PID, logged setpoint + actual | Kills thermal variance | Yes, but coarse (~5°C steps), log not exposed |
| Dry high heat | ≥250°C sear surface; Maillard needs >140°C + low moisture | Unlocks the browning half of the taste manifold | No (~160°C wet-heat cap) — the biggest manifold gap |
| Radiant/convection mode | 120–250°C bake/roast | Breads, roasts, gratins | No |
| Pressure cooking | ~2 bar / 120°C | Fast stocks, braises, legumes | No |
| Integrated scale | ±1 g, guided or automated dosing | Measurement variance → zero | Scale yes (±5 g), no auto-dosing |
| Automated ingredient sequencing | Hoppers / timed dispensers | Removes human timing variance; enables unattended CI runs | No — human adds on prompt |
| Pinned firmware | Versioned, reproducible programs | Compiler version pinning | Updates opaque, not pinnable |

### B. Observability — the instrument (the differentiator; no consumer machine has this)

| Capability | Spec | Serves | Thermomix today |
|---|---|---|---|
| Telemetry export | ~1 Hz: bowl/surface/probe temps, power, continuous mass, motor current | **Process traces**: (recipe, trace, outcome) triples = the ground-truth flywheel for L2; failed dishes get stack traces ("overshoot at step 4") instead of "it was bad" | Sensors exist internally; no export API |
| Viscosity proxy | Stirring-motor torque/current curve | Free thickness sensor (sauces, doughs, custards) | Implicitly present, unexposed |
| Evaporation curve | Continuous mass over time | Reduction/concentration state, machine-checkable | Scale exists, not continuously logged |
| Vessel camera | Color/texture tracking | "Until golden" becomes a measurable predicate; doneness classifiers | No |
| VOC / e-nose | MOS gas sensor array | Maillard onset, burn detection, aroma fingerprint | No (nothing on the consumer market) |
| Optional probes | pH, refractometer (Brix) | Acidity/sugar concentration checks | No |

### C. Closed-loop runtime — the language

| Capability | Spec | Serves | Thermomix today |
|---|---|---|---|
| Sensory-predicate termination | `until(color ≥ X ∨ VOC event ∨ viscosity ≥ Y)` with timeout fallback | Executes the IR's termination conditions directly — closes the tacit-knowledge gap (§2, lossy serialization) | Time/temp only |
| Conditional branching | If-then on sensor state (e.g., keep reducing until viscosity target) | Recipes become programs with control flow, not open-loop scripts | Linear guided steps only |
| Checkpointing | Pause states for human taste-and-adjust | Breakpoints / interactive debugging | Partial (manual pause) |
| Open program API | Upload arbitrary step programs | The chef LLM targets the machine directly | Closed platform; no public API for arbitrary programs |

### D. Residual variance — ingredients (protocol, not hardware)

After the machine is standardized, the last uncontrolled variable is ingredient quality (the same recipe with watery winter tomatoes is a different program input). Not solvable in hardware: pin ingredient lots/brands/Brix for eval runs and log ingredient metadata into the process trace. Borne by the CookEval protocol (§7.6).

### How to use this spec

1. **Scorecard:** Thermomix scores high on A, near-zero on B/C *exposure* — the gap is observability, not actuation.
2. **The lazy path — retrofit, don't build:** an instrumented eval rig *around* the beachhead machine (camera + IR thermometer + continuous-logging scale + cheap VOC sensor) delivers most of section B for a few hundred dollars, without hardware development. The trace flywheel does not need to wait for an ideal machine.
3. **Strategic payoff of B/C:** once sensory predicates are machine-checkable, doneness/state verification migrates from L3 (humans) to L2 (sensors + models) — human tastings shrink to pure hedonics, which is the scarce resource the whole architecture economizes.
