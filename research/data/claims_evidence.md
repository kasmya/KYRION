# Claims-to-Evidence Table

Every claim below must trace to the listed file. `UNBACKED`/`VERIFY`/`FILL`
means do that before writing the sentence.

| Section | Claim | Evidence file | Value / Status |
|---------|-------|---------------|----------------|
| Dataset | We evaluate 5 models across 20 tasks | `results_runs.csv` | 5 models, 297 runs |
| Dataset | Each cell has multiple repetitions (k>=3) | `results_runs.csv` | balanced ~60/model |
| Method | Hallucination detector validated against ground truth | `detector_validation.csv` | P=1.0, R=0.9783, F1=0.989 |
| Results | Model ranking on Trust Score (best: gpt-oss-120b) | `stats_trust_score.csv` | gpt-oss-120b=90.5; llama-3-3-nemotron-super-49b-v1=89.3; llama-3-3-70b-instruct=88.4; llama-3-1-70b-instruct=86.8; deepseek-v4-flash=86.1 |
| Results | Model ranking on Quality Score (best: gpt-oss-120b) | `stats_quality_score.csv` | gpt-oss-120b=86.0; llama-3-3-nemotron-super-49b-v1=83.3; llama-3-3-70b-instruct=82.5; deepseek-v4-flash=80.4; llama-3-1-70b-instruct=79.7 |
| Results | Model ranking on code smells (best: gpt-oss-120b) | `stats_code_smells.csv` | llama-3-1-70b-instruct=3.7; deepseek-v4-flash=2.8; llama-3-3-70b-instruct=2.3; llama-3-3-nemotron-super-49b-v1=2.2; gpt-oss-120b=1.5 |
| Results | Model ranking on true hallucinations (best: llama-3-3-nemotron-super-49b-v1) | `stats_hallucination_count.csv` | deepseek-v4-flash=0.3; llama-3-1-70b-instruct=0.2; llama-3-3-70b-instruct=0.2; gpt-oss-120b=0.2; llama-3-3-nemotron-super-49b-v1=0.2 |
| Results | Models are statistically indistinguishable on Trust/Quality | `stats_trust_score.csv, stats_quality_score.csv` | VERIFY: Kruskal-Wallis p>0.05 at task level (you reported p=0.36, 0.32) |
| Results | Models differ significantly on code smells | `stats_code_smells.csv` | VERIFY: H=12.65, p=0.013; gpt-oss vs llama-3.1 & deepseek significant (delta=0.52) |
| Results | Which specific smell types differ | `smell_breakdown.csv` | FILL after running phase2_smell_breakdown.py |
| Results | Conclusions robust to Trust-Score weighting | `weight_sensitivity.csv` | backed |

## Claims you must NOT make (write-time guardrails)

- Do NOT claim any model is 'unsafe' or 'dangerous' - not statistically supported
- Do NOT claim 'execution-based' detection - detector is static (AST)
- Do NOT claim significant Trust/Quality differences - they are tied
- Do NOT claim 'hallucination in every sample' - true rate is near zero
- Do NOT drop Holm correction to manufacture significance