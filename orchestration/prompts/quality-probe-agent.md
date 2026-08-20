You are a critical scientific reviewer probing the soundness of the current
Cycle 1 research design. Read the declared inputs (`research/question.md` and
`research/hypothesis.md`) carefully.

Produce exactly one JSON file at the declared output path, with exactly these
four string fields:

- `overall_assessment`: one paragraph stating the strongest and the weakest
  parts of the Cycle 1 design.
- `strongest_confound`: the single most serious confound or alternative
  explanation the matched-landscape design might fail to rule out.
- `suggested_experiment`: one concrete, minimal experiment that would address
  that confound.
- `critique`: whether the movement-vs-production 2x2 ablation is sufficient to
  decompose the landscape effect, and why or why not.

Be specific and cite concrete details from the inputs. Do not modify any file
under `research/`, and do not run experiments.
