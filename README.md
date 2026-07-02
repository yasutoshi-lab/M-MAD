# M-MAD: Multidimensional Multi-Agent Debate for Advanced Machine Translation Evaluation


## **🤖** About M-MAD<a name="about"></a>

The **M-MAD** framework is a systematic LLM-based multi-agent framework for advanced LLM-as-a-judge MT evaluation. It operates in three stages:

1. **Dimension Partition**: Decomposing the heuristic MQM annotation guideline into distinct dimensions for independent LLM-as-a-judge assessments.
2. **Multi-Agent Debate**: Conducting multi-agent debates within each dimension, harnessing LLMs' inherent knowledge, reasoning, and collaborative abilities.
3. **Final Judgment**: Synthesizing the debated outcomes through a final judge agent to produce a comprehensive evaluation judgment.

![framework.png](asset/framework.png)

## **📄** Paper

For a detailed explanation of the M-MAD framework, please refer to the paper:  
[Multidimensional Multi-Agent Debate for Advanced Machine Translation Evaluation (arXiv)](https://arxiv.org/pdf/2412.20127)

## Code Structure
- `code/`: Code and prompts for all stages
- `data/`: Input data and output-annotated data  
  Our input data is sourced from WMT-23 Metrics Shared Task. You can also downloaded it from [https://github.com/google-research/mt-metrics-eval](https://github.com/google-research/mt-metrics-eval) or https://wmt-metrics-task.github.io/.
- `metrics_scores/`: Meta-evaluation results
- `doc/`: Detailed documentation (architecture / usage / configuration / data formats / contributing; Japanese). Start from [doc/README.md](doc/README.md).
- `tests/`: Unit tests (pytest; run in CI together with ruff lint)

## **💻** Running the Code

### 1) Environment Setup ###

We use [uv](https://docs.astral.sh/uv/) with Python 3.10 for environment management.

```bash
git clone https://github.com/SU-JIAYUAN/M-MAD.git
cd M-MAD
uv sync                 # create the virtualenv and install runtime dependencies (Python 3.10)
uv sync --group eval    # additionally install meta-evaluation deps (numpy, mt-metrics-eval); only needed for step 4
```

Run any command inside the environment with `uv run` (e.g. `uv run python code/stage1.py --help`).

#### Tests / Lint

```bash
uv run pytest tests/ -q     # unit tests
uv run ruff check code tests  # lint (ruff)
uv run pre-commit install   # (optional) enable local pre-commit ruff hook
```

Tests and lint also run automatically in CI (GitHub Actions) on push / PR to `main`.

#### LLM provider (OpenAI / Gemini / Vertex / Anthropic)

The LLM backend is selected via environment variables (loaded automatically from a `.env` file at the repo root; see `.env.example` and [doc/configuration.md](doc/configuration.md)).

```bash
cp .env.example .env
# then edit .env
```

- **Vertex AI / Agent Platform (OpenAI-compatible endpoint, ADC OAuth)** — recommended for Google Cloud:
  ```
  LLM_PROVIDER=vertex
  LLM_MODEL=gemini-3.5-flash          # google/ prefix is added automatically
  GCP_PROJECT=your-gcp-project-id
  LLM_LOCATION=global
  ```
  Run `gcloud auth application-default login` first (no API key needed). Uses
  `base_url=https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/endpoints/openapi`.
- **Gemini (Google AI Studio, static API key)**:
  ```
  LLM_PROVIDER=gemini
  LLM_MODEL=gemini-3.5-flash
  GEMINI_API_KEY=your-gemini-api-key
  ```
  Uses `base_url=https://generativelanguage.googleapis.com/v1beta/openai/`.
- **OpenAI** (default): set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` (default model: `gpt-4.1-mini`).
- **Anthropic**: set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` (default model: `claude-haiku-4-5`, via the OpenAI-compatible endpoint `https://api.anthropic.com/v1/`).

### 2) Stage 1 (Dimension Partition)

```bash
sh run_stage1.sh
```

### 3) Stage 2 & 3 (Muti-Agent Debate & Final Judgement)

```bash
sh run_stage2_3.sh
```

### 4) Meta-evaluation

To run the meta-evaluation for the metrics, execute the following file, where we use the evaluation tool from https://github.com/google-research/mt-metrics-eval.

```bash
wmt23_metrics.ipynb
```

## Fork Extensions (ja → multilingual diagnosis)

This fork adds tooling for diagnosing Japanese-to-multilingual MT quality with M-MAD as the judge, while keeping the paper's method unchanged (single-provider runs, 3 stages, MQM 4 dimensions):

- **Input preprocessing** (`code/prepare_input.py`): converts instruction-manual JSON (`.input/<manual_id>/`) into Stage1 tab-separated inputs plus a segment map. See [doc/usage.md](doc/usage.md).
- **Shared ja→en 4-shot demos** (`code/few_shot_demos_ja.py`): applied to all `ja-*` language pairs via source-language resolution. See [doc/prompts-and-fewshot.md](doc/prompts-and-fewshot.md).
- **Run-level jury** (`code/run_jury.py`): runs the whole pipeline independently per provider (OpenAI / Anthropic / Vertex) with separated output directories — each run stays single-provider (paper-compliant).
- **Agreement report** (`code/jury_report.py`): read-only post-processing that juxtaposes per-provider scores and descriptive agreement statistics (Spearman ρ, Cohen's κ). No combined score is produced.

Reliability: total API failures are surfaced as `success: false` + `api_failures` in Stage1 outputs, permanent 4xx errors fail fast (no retry), and outputs record the actually used `model_name` / `provider`.

## Citation

```
@article{feng2024mmad,
  title={M-MAD: Multidimensional Multi-Agent Debate Framework for Fine-grained Machine Translation Evaluation},
  author={Feng, Zhaopeng and Su, Jiayuan and Zheng, Jiamei and Ren, Jiahan and Zhang, Yan and Wu, Jian and Wang, Hongwei and Liu, Zuozhu},
  journal={arXiv preprint arXiv:2412.20127},
  year={2024}
}
```