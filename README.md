# NL → FOL Translator, Validators, KB, Proofs, and Benchmarks

This repository provides a modular pipeline to translate English natural language (NL) into First-Order Logic (FOL), validate generated formulas via multiple parsers, store and query logic in a knowledge base with derivation traces, and evaluate performance using datasets and benchmarking scripts.

All core functions are accessible via the unified `main.py` entrypoint and dedicated CLIs.

## 1. Folder Structure

```
translator/        # NL→FOL translator engine + rules
  translator.py    # Main translation function
  matcher.py       # Rule-based pattern matching
  templates.py     # Rendering and interpolation utilities
  fol_validator.py # Lark grammar syntax validator (common notation)
  nlp.py           # spaCy pipeline loader
  data_structures.py
  rules.yaml       # YAML rule definitions for translation

method_lark/       # Lark-based validator
  validator.py
method_nltk/       # NLTK LogicParser validator
  validator.py
method_fomaster/   # Lightweight custom validator
  adapter.py
  fol_syntax_semantics.py
  validator.py

knowledge_base/    # pyDatalog-backed KB with tracing
  engine.py
  __init__.py

proof/             # Natural Deduction proof system
  engine.py
  parser.py
  nd_prover.py
  ast_nodes.py

resolution_engine/ # Classical CNF Resolution prover
  Resolution.py
  Statement.py
  Predicate.py
  Runner.py

benchmarks/        # Datasets, metrics, runners
  run_translation.py
  metrics.py
  registry.py
  fol_analysis.py
  types.py
  datasets/
    base.py
    folio.py

data/              # Persistent KB store, test sets
results/           # Benchmark outputs (JSON/JSONL)
scripts/           # Utilities (debug, compare)

main.py            # CLI for translation + validation
kb_cli.py          # CLI for KB operations
proof_cli.py       # CLI for ND proofs
compare_outputs.py # Compare two benchmark runs
requirements.txt   # Python dependencies
```

## 2. Installation

Python 3.10+ recommended.

```bash
# (Optional) create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download spaCy model (required for NLP processing)
python -m spacy download en_core_web_sm
```

## 3. Usage

Translate and validate one or more sentences:

```bash
python main.py --method lark "All humans are mortal" "Some cats are animals"
python main.py --method nltk "If all humans are mortal then Socrates is mortal"
python main.py --method fomaster "All daisies are flowers"
python main.py --all "All humans are mortal" "If Some daisies are flowers then All daisies are flowers"
```

Example output:

```
NL: All humans are mortal
FOL: forall x. (Human(x) -> Mortal(x))
  lark: True
  nltk: True
  fomaster: True
```

## 4. Translation Pipeline Overview

1. spaCy processes the sentence → tokens & dependencies.
2. Rule matcher (`translator/rules.yaml`) captures semantic fragments (quantifiers, predicates, implication patterns).
3. Templates assemble pieces into structured FOL.
4. A small Lark grammar checks syntactic well-formedness.
5. Optional re-validation by method-specific validators (`method_lark`, `method_nltk`, `method_fomaster`).

## 5. Validators

- All validators accept common FOL notation (`forall/exists`, `&`, `|`, `->`, `<->`, `=`).
- `method_lark`: strict grammar-based parsing.
- `method_nltk`: NLTK LogicParser with notation normalization.
- `method_fomaster`: lightweight, resilient tokenization + structure checks.

## 6. Knowledge Base (KB)

Use `kb_cli.py` to manage facts and rules.

- Add: `python kb_cli.py add "All humans are mortal"`
- Query: `python kb_cli.py query "Is Socrates mortal?"`
- List: `python kb_cli.py list`
- Clear: `python kb_cli.py clear`

KB features:
- pyDatalog-backed environment (`exec/eval`) with persistent state in `data/kb_store.json`.
- Facts: `Human(Socrates)` → `+ Human('Socrates')`.
- Rules: `forall x. (A(x) & B(x) -> C(x))` → `C(X) <= A(X) & B(X)` with derivation logging.
- Queries: existential and direct fact queries return `(entailed, trace)`.

## 7. Natural Deduction Prover

Use `proof_cli.py` for interactive ND proofs.

Supported connectives and quantifiers: `not`, `&`, `|`, `->`, `<->`, `forall`, `exists` (and Unicode variants).

Example (derive `Mortal(Socrates)`):

```
Premises:
forall x. (Human(x) -> Mortal(x))
Human(Socrates)

Commands:
R 1
AE 0 Socrates
>E 2 3
Finish
```

## 8. Resolution Prover

`resolution_engine/` implements classical CNF resolution:
- CNF conversion (implication removal, De Morgan’s, distribution, standardization).
- Iterative clause resolution to detect contradictions against a negated query.
- File-driven `run_resolution_engine(input_file, output_file)` interface.

## 9. Benchmarks & Results

Run translation benchmarking against datasets:

```bash
python benchmarks/run_translation.py --dataset folio --output results/folio_rows.jsonl
python benchmarks/run_translation.py --dataset folio --summary results/folio_summary.json
```

Compare two runs (rows or summaries):

```bash
python compare_outputs.py results/baseline.json results/new.json --mode translation
python compare_outputs.py results/baseline.jsonl results/new.jsonl --mode translation
```

Metrics include: parsing BLEU, exact match, predicate precision/recall/F1, tree similarity, translation rate, and per-validator pass/fail counts.

## 10. Adding New Rules

Edit `translator/rules.yaml` to introduce new pattern mappings. Re-run sentences to see updated translations. Keep patterns conservative to avoid over-matching.

## 11. Troubleshooting

- spaCy model error: Run `python -m spacy download en_core_web_sm`.
- NLTK parse failures: The NLTK LogicParser is stricter; simplify or parenthesize expressions.
- FO-Master rejection: Check implications and parentheses around complex antecedents.
- Unexpected translation: Inspect intermediate tokens in `translator/matcher.py`.

## 12. Extending Validators

Add a new folder `method_<name>/` with a `validator.py` exposing `validate(fol: str) -> bool`. Register it inside `main.py` in the `METHODS` mapping.

## 13. Licensing & Attribution

External libraries: spaCy, Lark, NLTK, pyDatalog.

## 14. Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python main.py --all "All humans are mortal" "Some dogs are animals"
```

## 15. Support

Open issues or extend validators/rules incrementally. Benchmarks and `compare_outputs.py` help track improvements over time.
