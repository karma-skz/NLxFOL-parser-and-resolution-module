"""
A robust Knowledge Base backed by pyDatalog.
Acts as a bridge between NL-to-FOL parsers and the Logic Programming engine.
"""

from __future__ import annotations
import re
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Set
from pyDatalog import pyDatalog

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KnowledgeBase:
    NEG_PREFIX = "NEG_"
    _literal_regex = re.compile(
        r"(?P<neg>not\s+)?(?P<pred>[A-Z][A-Za-z0-9_]*)\((?P<args>[^()]+)\)"
    )

    def __init__(self) -> None:
        # 1. Logic Environment (Persistent Scope for exec/eval)
        # This dictionary acts as the "memory" for pyDatalog variables.
        self.logic_env: Dict[str, Any] = {}

        # Bootstrap the environment: Import pyDatalog INSIDE the env so exec() can use it
        exec("from pyDatalog import pyDatalog", self.logic_env)

        # Initialize Global Variables X, Y, Z inside the env
        # We use create_terms inside exec to force injection into self.logic_env
        exec("pyDatalog.create_terms('X, Y, Z, _Trace, _log_step')", self.logic_env)

        # Trace Storage
        self.trace_log: List[str] = []

        # Define and inject the logging function
        def _log_step_impl(pred, entity):
            val = entity
            # Unwrap pyDatalog tuples/lists
            while isinstance(val, (list, tuple)) and len(val) == 1:
                val = val[0]

            # If it's still a list/tuple (e.g. multiple args), format it nicely
            if isinstance(val, (list, tuple)):
                val_str = ", ".join(str(v) for v in val)
            else:
                val_str = str(val)

            pretty_pred = self._format_predicate_name(pred)
            self.trace_log.append(f"Derived {pretty_pred}({val_str})")
            return True

        self.logic_env["_log_step"] = _log_step_impl

        # 2. Internal State Storage (for UI/API listing)
        self.state: Dict[str, Any] = {
            "facts": set(),
            "rules": set(),
            "raw_formulas": [],
        }

        # 3. Dynamic Predicate Registry
        self._predicates: Set[str] = set()

        # 4. Persistence
        root = Path(__file__).resolve().parents[1]
        self._store_path = root / "kb_store.json"

        # Load state
        self._load()

    # ==========================================
    # CORE API Methods (Used by CLI)
    # ==========================================

    def add(self, fol: str) -> bool:
        """
        Adds a FOL sentence to the KB.
        Supports:
        - Facts: Human(Socrates)
        - Rules: forall x. (Human(x) -> Mortal(x))
        """
        fol = fol.strip()
        if not fol:
            return False

        try:
            # 1. Try Parse as Fact
            if self._try_add_fact(fol):
                self.state["facts"].add(fol)
                self._save()
                return True

            # 2. Try Parse as Rule
            if self._try_add_rule(fol):
                self.state["rules"].add(fol)
                self._save()
                return True

            # 3. Store but warn if unsupported
            logger.warning(f"Formula stored but not executable: {fol}")
            self.state["raw_formulas"].append(fol)
            self._save()
            return True

        except Exception as e:
            logger.error(f"Error adding formula '{fol}': {e}")
            return False

    def query(self, fol: str) -> Tuple[bool, List[str]]:
        """
        Queries the KB.
        Returns: (is_entailed, proof_trace)
        """
        fol = fol.strip()
        trace = []

        try:
            # 1. Existential Query: "Some friends are toxic"
            # Pattern: exists x. (A(x) & B(x))
            exist_match = re.match(
                r"^\s*exists\s+[a-z]\.\s*\((.+)\)\s*$", fol, re.IGNORECASE
            )
            if exist_match:
                body = exist_match.group(1)
                # Convert "A(x) & not B(x)" -> "A(X) & __not__B(X)"
                datalog_query = self._convert_body_to_datalog(body)
                for token in re.findall(r"([A-Z_][A-Za-z0-9_]*)\(", datalog_query):
                    if token.startswith("_"):
                        continue
                    self._ensure_predicate(token)
                trace.append(f"Executing Query: {datalog_query}")
                self.trace_log.clear()

                # Ask pyDatalog using the persistent logic environment
                try:
                    # eval returns a list of results (tuples) if successful
                    results = eval(datalog_query, self.logic_env)
                except Exception as e:
                    trace.append(f"Engine evaluation failed: {e}")
                    return False, trace

                if results and len(results) > 0:
                    trace.append(f"Success! Witnesses found: {results}")
                    return True, trace
                else:
                    trace.append("No witnesses found satisfying the condition.")
                    return False, trace

            # 2. Specific Fact Query: "Mortal(Socrates)"
            literal = self._parse_fact_literal(fol)
            if literal:
                pred, args, negated = literal
                encoded_pred = self._encode_predicate(pred, negated)
                self._ensure_predicate(encoded_pred)

                args_code, args_display = self._format_arguments_for_fact(args)
                query_str = f"{encoded_pred}({args_code})"
                friendly_pred = self._format_predicate_name(encoded_pred)
                trace.append(f"Checking Fact: {friendly_pred}({args_display})")

                # Clear previous trace log
                self.trace_log.clear()

                try:
                    results = eval(query_str, self.logic_env)
                except Exception as e:
                    trace.append(f"Engine evaluation failed: {e}")
                    return False, trace

                if results:
                    trace.append(
                        f"Fact verified. {friendly_pred}({args_display}) is True."
                    )
                    if self.trace_log:
                        trace.append("Derivation Steps:")
                        trace.extend([f"  - {step}" for step in self.trace_log])
                    return True, trace
                else:
                    trace.append("Fact cannot be proven.")
                    return False, trace

            # 3. Fallback
            return False, ["Query format not supported by this engine."]

        except Exception as e:
            logger.error(f"Query Error: {e}")
            return False, [f"Error during inference: {str(e)}"]

    def clear(self) -> None:
        """Resets the Knowledge Base."""
        self.state = {"facts": set(), "rules": set(), "raw_formulas": []}
        self.trace_log = []
        # Reset Logic
        # We clear the logic env and re-bootstrap
        self.logic_env = {}
        exec("from pyDatalog import pyDatalog", self.logic_env)
        exec("pyDatalog.create_terms('X, Y, Z, _Trace, _log_step')", self.logic_env)

        # Re-inject logging function
        def _log_step_impl(pred, entity):
            val = entity
            while isinstance(val, (list, tuple)) and len(val) == 1:
                val = val[0]

            if isinstance(val, (list, tuple)):
                val_str = ", ".join(str(v) for v in val)
            else:
                val_str = str(val)

            pretty_pred = self._format_predicate_name(pred)
            self.trace_log.append(f"Derived {pretty_pred}({val_str})")
            return True

        self.logic_env["_log_step"] = _log_step_impl

        self._predicates.clear()
        self._save()

    # ==========================================
    # API HELPER FUNCTIONS
    # ==========================================

    def get_state(self) -> Dict[str, Any]:
        return {
            "facts": list(sorted(self.state["facts"])),
            "rules": list(sorted(self.state["rules"])),
            "other": list(self.state["raw_formulas"]),
            "stats": {
                "fact_count": len(self.state["facts"]),
                "rule_count": len(self.state["rules"]),
                "active_predicates": list(self._predicates),
            },
        }

    def list_facts(self) -> List[str]:
        return list(sorted(self.state["facts"]))

    def list_rules(self) -> List[str]:
        return list(sorted(self.state["rules"]))

    def list_other(self) -> List[str]:
        return list(sorted(self.state["raw_formulas"]))

    def backward_query(self, fol: str) -> Tuple[bool, List[str]]:
        return self.query(fol)

    # ==========================================
    # INTERNAL LOGIC & PARSING
    # ==========================================

    def _ensure_predicate(self, name: str):
        """Register a predicate in the Logic Environment if new."""
        if name not in self.logic_env:
            # Robust Creation: Execute create_terms INSIDE the logic_env
            # This forces pyDatalog to inject the 'name' key into logic_env
            exec(f"pyDatalog.create_terms('{name}')", self.logic_env)
            self._predicates.add(name)

    def _try_add_fact(self, fol: str) -> bool:
        """Parses 'Human(Socrates)' -> + Human('Socrates')"""
        parsed = self._parse_fact_literal(fol)
        if not parsed:
            return False

        pred, args, negated = parsed
        encoded_pred = self._encode_predicate(pred, negated)
        self._ensure_predicate(encoded_pred)

        args_code, _ = self._format_arguments_for_fact(args)

        # Execute in logic_env
        code = f"+ {encoded_pred}({args_code})"
        try:
            exec(code, self.logic_env)
            logger.info(f"Executed: {code}")
            return True
        except Exception as e:
            logger.error(f"Fact assert failed: {e}")
            return False

    def _try_add_rule(self, fol: str) -> bool:
        """Parses 'forall x. (A(x) & B(x) -> C(x))' -> C(X) <= A(X) & B(X)"""
        if "->" not in fol:
            return False

        clean = re.sub(r"^\s*forall\s+[a-z]\.\s*", "", fol).strip()
        if clean.startswith("(") and clean.endswith(")"):
            clean = clean[1:-1]

        try:
            ante_str, cons_str = clean.split("->")
        except ValueError:
            return False

        datalog_head = self._convert_body_to_datalog(cons_str)
        datalog_body = self._convert_body_to_datalog(ante_str)

        if not datalog_head or not datalog_body:
            return False

        # Extract Predicates to ensure they exist in env
        combined = f"{datalog_head} {datalog_body}"
        for token in re.findall(r"([A-Z]\w*)\(", combined):
            self._ensure_predicate(token)

        # Inject Tracing
        # Attempt to extract head predicate and variable to add logging
        # Head format expected: Predicate(X)
        match = re.match(r"^\s*([A-Z]\w*)\(([^)]+)\)\s*$", datalog_head)
        if match:
            pred_name, var_name = match.groups()
            # Append trace clause: & (_Trace == _log_step('Pred', Var))
            code = f"{datalog_head} <= {datalog_body} & (_Trace == _log_step('{pred_name}', {var_name}))"
        else:
            code = f"{datalog_head} <= {datalog_body}"

        try:
            exec(code, self.logic_env)
            logger.info(f"Executed Rule: {code}")
            return True
        except Exception as e:
            logger.error(f"Rule Execution Failed: {code} | Error: {e}")
            return False

    def _convert_body_to_datalog(self, expr_str: str) -> str:
        expr = expr_str.replace(" and ", " & ").replace(" or ", " | ")

        def _replace_literal(match: re.Match) -> str:
            is_neg = bool(match.group("neg"))
            pred = match.group("pred")
            args = match.group("args")
            encoded = self._encode_predicate(pred, is_neg)
            norm_args = self._normalize_arguments(args)
            return f"{encoded}({norm_args})"

        transformed = self._literal_regex.sub(_replace_literal, expr)
        return transformed.strip()

    def _encode_predicate(self, name: str, negated: bool) -> str:
        return f"{self.NEG_PREFIX}{name}" if negated else name

    def _format_predicate_name(self, encoded: str) -> str:
        if encoded.startswith(self.NEG_PREFIX):
            return f"not {encoded[len(self.NEG_PREFIX):]}"
        return encoded

    def _normalize_arguments(self, args_str: str) -> str:
        args = [arg.strip() for arg in args_str.split(",")]
        normalized: List[str] = []
        for arg in args:
            if re.fullmatch(r"[a-z]", arg):
                normalized.append(arg.upper())
            else:
                normalized.append(arg)
        return ", ".join(normalized)

    def _parse_fact_literal(self, fol: str) -> Optional[Tuple[str, List[str], bool]]:
        m = re.match(r"^\s*(not\s+)?([A-Z][A-Za-z0-9_]*)\(([^()]+)\)\s*$", fol)
        if not m:
            return None

        negated = bool(m.group(1))
        pred = m.group(2)
        args_raw = [arg.strip() for arg in m.group(3).split(",")]
        if not all(args_raw):
            return None
        return pred, args_raw, negated

    def _quote_constant(self, value: str) -> str:
        stripped = value.strip()
        if (stripped.startswith("'") and stripped.endswith("'")) or (
            stripped.startswith('"') and stripped.endswith('"')
        ):
            stripped = stripped[1:-1]
        escaped = stripped.replace("'", "\\'")
        return f"'{escaped}'"

    def _format_arguments_for_fact(self, args: List[str]) -> Tuple[str, str]:
        code_args = ", ".join(self._quote_constant(arg) for arg in args)
        display_parts = []
        for arg in args:
            token = arg.strip()
            if (token.startswith("'") and token.endswith("'")) or (
                token.startswith('"') and token.endswith('"')
            ):
                token = token[1:-1]
            display_parts.append(token)
        display_args = ", ".join(display_parts)
        return code_args, display_args

    # ==========================================
    # PERSISTENCE
    # ==========================================

    def _save(self) -> None:
        try:
            data = {
                "facts": list(self.state["facts"]),
                "rules": list(self.state["rules"]),
                "other_formulas": self.state["raw_formulas"],
            }
            with open(self._store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save KB: {e}")

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        try:
            with open(self._store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for fact in data.get("facts", []):
                    self.add(fact)
                for rule in data.get("rules", []):
                    self.add(rule)
                for other in data.get("other_formulas", []):
                    self.state["raw_formulas"].append(other)
            logger.info("KB State Loaded from Disk.")
        except Exception as e:
            logger.error(f"Failed to load KB: {e}")


# Singleton Accessor
_global_kb: Optional[KnowledgeBase] = None


def kb() -> KnowledgeBase:
    global _global_kb
    if _global_kb is None:
        _global_kb = KnowledgeBase()
    return _global_kb
