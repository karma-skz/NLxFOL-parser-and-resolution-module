# FOLIO Benchmark Commands

> Run everything from the repository root in Windows PowerShell.

## Rule-Based Translator (`run_nlmodel.py`)

```powershell
python benchmarks\run_nlmodel.py --split validation --limit-examples 10 --output-jsonl outputs\folio\nlmodel_rows.jsonl --summary-json outputs\folio\nlmodel_summary.json --no-progress
```

## Gemini Baseline (`run_gemini.py`)

Set GLE_API_KEY` (or pass pi-key`) and ensure install -r requirements.txt` has been run:

```powershell
python benchmarks\run_gemini.py --split validation --limit-examples 10 --model gemini-2.0-flash --output-jsonl outputs\folio\gemini_rows.jsonl --summary-json outputs\folio\gemini_summary.json --no-progress
```

## Inspect Raw FOLIO Data (first 10 lines)

```powershell
Get-Content benchmarks\datasets\FOLIO\data\v0.0\folio-validation.jsonl -TotalCount 10
```

## get report

```bash
python benchmarks\report_translation_comparison.py --parser-rows outputs\folio\nlmodel_rows.jsonl --gemini-rows outputs\folio\gemini_rows.jsonl --parser-summary outputs\folio\nlmodel_summary.json --gemini-summary outputs\folio\gemini_summary.json --output outputs\folio\comparison.txt --parser-label "Rule Parser" --gemini-label "Gemini Flash"
```
