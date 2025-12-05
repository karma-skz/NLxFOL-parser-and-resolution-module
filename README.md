# NL → FOL Translator & Multi-Validator

This project provides a single natural language (English) to first-order logic (FOL) translator shared across three independent validation methods:

- Lark-based grammar parser
- NLTK LogicParser
- FO Master style (lightweight validator; common notation)

All methods are accessible via the unified `main.py` entrypoint.

## 1. Folder Structure

```
translator/        # NL→FOL translator engine + rules
  translator.py    # Main translation function
  matcher.py       # Rule-based pattern matching
  templates.py     # Rendering and interpolation utilities
  fol_validator.py # Lark grammar syntax validator
  nlp.py           # spaCy pipeline loader
  data_structures.py
  rules.yaml       # YAML rule definitions for translation
knowledge_base/    # pyDatalog-backed KB helper (engine.py)
benchmarks/        # Dataset loaders, LLM harnesses, metrics
method_lark/       # Lark validator wrapper
method_nltk/       # NLTK LogicParser validator
method_fomaster/   # Lightweight validator using common notation
main.py            # Command-line interface
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
```

Run all validators at once (recommended while exploring):

```bash
python main.py --all "All humans are mortal" "If Some daisies are flowers then All daisies are flowers"

python compare_outputs.py outputs/folio/parser_validation_summary.json outputs/folio/llm_gemini_validation_summary.json --first-label parser --second-label gemini

python -m benchmarks.folio_gemini_runner --split validation --unit sentence --model gemini:gemini-2.0-flash --cache --output-jsonl outputs/folio/llm_validation_rows.jsonl --summary-json outputs/folio/llm_validation_summary.json
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
4. Lark validator checks syntactic well-formedness before returning.
5. Each method folder re-validates using its own approach when invoked.

## 5. Notes on Validators

- All three methods now accept the same FOL notation (`forall/exists`, `&`, `|`, `->`, `<->`, `=`).
- The FO Master method is intentionally lightweight and permissive; it checks tokenization and structure only.

## 6. Adding New Rules

Edit `translator/rules.yaml` to introduce new pattern mappings. After changes, re-run sentences to see updated translations. Keep patterns conservative to avoid over-matching.

## 7. Troubleshooting

- spaCy model error: Run `python -m spacy download en_core_web_sm`.
- NLTK parse failures: The NLTK LogicParser is stricter; simplify or parenthesize expressions.
- FO Master rejection: Check for malformed implications or missing parentheses around complex antecedents.
- Unexpected translation: Inspect intermediate tokens by temporarily adding print statements in `translator/matcher.py`.

## 8. Extending Validators

Add a new folder `method_<name>/` with a `validator.py` exposing `validate(fol: str) -> bool`. Register it inside `main.py` in the `METHODS` mapping.

## 9. Licensing & Attribution

Original NL→FOL rule and template approach adapted from the provided project context. External libraries: spaCy, Lark, NLTK.

## 10. Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python main.py --all "All humans are mortal" "Some dogs are animals"
```

## 11. Support

For clarification or enhancements, add issues or extend validators. Keep rule additions incremental.

## 12. Knowledge Base & Prover

The project includes a Knowledge Base (KB) and a Natural Deduction Prover, accessible via CLI tools.

### 12.1 Knowledge Base (CLI)

Use `kb_cli.py` to manage facts and rules.

- Add: `python kb_cli.py add "All humans are mortal"`
- Query: `python kb_cli.py query "Is Socrates mortal?"`
- List: `python kb_cli.py list`
- Clear: `python kb_cli.py clear`

### 12.2 KB Limitations

The KB remains intentionally restricted for predictability and performance:

- Only unary predicates (e.g., `Human(Socrates)`), no binary relations.
- Rules must be universally quantified over a single variable with conjunctive antecedent/consequent.
- No negation, disjunction, or equality reasoning inside the KB; use the ND prover for those.
- Existentials are handled by witness introduction during `add`, not by general Skolem functions.
- Constants come from translator formatting (proper nouns maintained as constants).

### 12.3 Natural Deduction Proof (Prover)

Use `proof_cli.py` for interactive proofs.

- Premises: enter one FOL formula per line (same syntax as validators).
- Commands:
  - `Assume <formula>`: open a subproof with the formula as an assumption
  - `R <i>`: recall (cite) line `<i>` (premises indexed from 0; proof lines continue after the divider)
  - `^I <i> <j>`: conjunction introduction from lines `<i>`, `<j>`
  - `^EL <i>` / `^ER <i>`: conjunction elimination (left/right) from line `<i>`
  - `>E <i> <j>`: implication elimination (modus ponens) using `<i>` (antecedent) and `<j>` (conditional)
  - `->I <a> <b>`: implication introduction, from assumption line `<a>` to conclusion line `<b>`
  - `AE <i> <Const>` (aka `∀E`): universal elimination instantiating the variable with `Const`
  - `Finish`: stop and render current proof

Supported connectives and quantifiers: `not`, `&`, `|`, `->`, `<->`, `forall`, `exists`, plus Unicode variants.

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

FOL resolution master is a tool for resolution of
