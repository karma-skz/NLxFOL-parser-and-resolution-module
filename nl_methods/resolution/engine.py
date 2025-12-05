"""FOL resolution engine ported from the legacy standalone project."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

from .predicate import Predicate
from .statement import Statement

UPPER_ALPHA_MAPPING = [chr(i) for i in range(ord("A"), ord("Z") + 1)]
LOWER_ALPHA_MAPPING = [chr(i) for i in range(ord("a"), ord("z") + 1)]
OPERATOR_PRIORITY = {"~": 4, "&": 3, "|": 2, "=>": 1}
TRUE = "TRUE"
FALSE = "FALSE"
KILL_LIMIT = 8000

PREDICATES_DICT: Dict[str, str] = {}
STANDARD_VARIABLE_COUNT = 0
KNOWLEDGE_BASE_HASH: Dict[str, Set[Statement]] = {}
KNOWLEDGE_BASE: Set[Statement] = set()


class Node:
    """Expression tree node used during CNF conversion."""

    def __init__(self, value: str):
        self.value = value
        self.negation = False
        self.operator = True
        self.left: Node | None = None
        self.right: Node | None = None
        if value in PREDICATES_DICT:
            if "~" in PREDICATES_DICT[value]:
                self.negation = True
                PREDICATES_DICT[value] = PREDICATES_DICT[value][1:]
            self.operator = False


def reset_state() -> None:
    global PREDICATES_DICT, STANDARD_VARIABLE_COUNT, KNOWLEDGE_BASE, KNOWLEDGE_BASE_HASH
    PREDICATES_DICT = {}
    STANDARD_VARIABLE_COUNT = 0
    KNOWLEDGE_BASE = set()
    KNOWLEDGE_BASE_HASH = {}


def inorder_traversal(node: Node | None) -> str:
    traversal: List[str] = []

    def inorder(n: Node | None) -> None:
        if n is None:
            return
        inorder(n.left)
        token = ("~" if n.negation else "") + n.value
        traversal.append(token)
        inorder(n.right)

    inorder(node)
    return "".join(traversal)


def give_constant(count: int, uppercase: bool) -> str:
    start = count + 26
    str_constant = ""
    while start >= 26:
        val = start % 26
        alphabet = UPPER_ALPHA_MAPPING if uppercase else LOWER_ALPHA_MAPPING
        str_constant = alphabet[val] + str_constant
        start //= 26
    alphabet = UPPER_ALPHA_MAPPING if uppercase else LOWER_ALPHA_MAPPING
    str_constant = alphabet[start - 1] + str_constant
    return str_constant


def distribute_and_over_or(node: Node | None) -> None:
    if node is None:
        return
    if node.value == "|" and node.left and node.right:
        if node.left.value == "&" and node.right.value == "&":
            left_and = node.left
            right_and = node.right
            a = left_and.left
            b = left_and.right
            c = right_and.left
            d = right_and.right
            if not all([a, b, c, d]):
                return
            a_copy = copy.deepcopy(a)
            b_copy = copy.deepcopy(b)
            c_copy = copy.deepcopy(c)
            d_copy = copy.deepcopy(d)
            left_or_1 = Node("|")
            left_or_2 = Node("|")
            right_or_1 = Node("|")
            right_or_2 = Node("|")
            node.value = "&"
            left_and.left = left_or_1
            left_and.right = left_or_2
            right_and.left = right_or_1
            right_and.right = right_or_2
            left_or_1.left = a
            left_or_1.right = c
            left_or_2.left = a_copy
            left_or_2.right = d
            right_or_1.left = b
            right_or_1.right = c_copy
            right_or_2.left = b_copy
            right_or_2.right = d_copy
        elif node.left.operator and not node.right.operator and node.left.value == "&":
            if node.left.right is None or node.right is None:
                return
            c = node.left.right
            a = node.right
            a_copy = copy.deepcopy(a)
            right_or = Node("|")
            node.value = "&"
            node.left.value = "|"
            node.left.right = a
            node.right = right_or
            right_or.left = c
            right_or.right = a_copy
        elif not node.left.operator and node.right.operator and node.right.value == "&":
            if node.left is None or node.right.left is None:
                return
            a = node.left
            a_copy = copy.deepcopy(a)
            b = node.right.left
            left_or = Node("|")
            node.value = "&"
            node.right.value = "|"
            node.left = left_or
            left_or.left = a
            left_or.right = b
            node.right.left = a_copy
    distribute_and_over_or(node.left)
    distribute_and_over_or(node.right)


def propagate_negation(node: Node | None) -> None:
    if node is None:
        return
    if node.operator and node.negation and node.left and node.right:
        node.left.negation = not node.left.negation
        node.right.negation = not node.right.negation
        node.value = "|" if node.value == "&" else "&"
        node.negation = False
    propagate_negation(node.left)
    propagate_negation(node.right)


def remove_implication(node: Node | None) -> None:
    if node is None:
        return
    remove_implication(node.left)
    if node.operator and node.value == "=>" and node.left:
        node.value = "|"
        node.left.negation = not node.left.negation
    remove_implication(node.right)


def convert_postfix_to_tree(statement: str) -> Node:
    stack: List[Node] = []
    r = re.compile(r"(~|&|\||=>|[A-Z][A-Z])")
    predicates = r.findall(statement)
    for token in predicates:
        if token in ["&", "|", "=>"]:
            operand2 = stack.pop()
            operand1 = stack.pop()
            operator = Node(token)
            operator.left = operand1
            operator.right = operand2
            stack.append(operator)
        elif token == "~":
            stack[-1].negation = not stack[-1].negation
        else:
            stack.append(Node(token))
    return stack[0]


def convert_to_postfix(statement: str) -> str:
    stack: List[str] = []
    r = re.compile(r"(~|&|\||=>|[A-Z][A-Z]|\(|\))")
    tokens = r.findall(statement)
    postfix: List[str] = []
    for token in tokens:
        if re.match(r"[A-Z][A-Z]", token):
            postfix.append(token)
        elif token in ["~", "&", "|", "=>"]:
            while (
                stack
                and stack[-1] not in ["(", ")"]
                and OPERATOR_PRIORITY[stack[-1]] >= OPERATOR_PRIORITY[token]
            ):
                postfix.append(stack.pop())
            stack.append(token)
        elif token == "(":
            stack.append(token)
        elif token == ")":
            while stack and stack[-1] != "(":
                postfix.append(stack.pop())
            if stack:
                stack.pop()
    while stack:
        postfix.append(stack.pop())
    return "".join(postfix)


def replace_predicate_by_constant(statement: str) -> tuple[str, Dict[str, str]]:
    r = re.compile(r"~?[A-Z][A-Za-z]*\([a-zA-Z][a-zA-Z,]*\)")
    predicates = r.findall(statement)
    mapping: Dict[str, str] = {}
    for index, predicate in enumerate(set(predicates)):
        predicate_constant = give_constant(index, True)
        mapping[predicate_constant] = predicate
        statement = statement.replace(predicate, predicate_constant)
    return statement, mapping


def replace_constant_by_predicate(statement: str, mapping: Dict[str, str]) -> str:
    for key, value in mapping.items():
        statement = statement.replace(key, value)
    return statement


def standardize_variables(statements: Iterable[str]) -> List[str]:
    global STANDARD_VARIABLE_COUNT
    standardized: List[str] = []
    for statement in statements:
        variable_dict: Dict[str, str] = {}
        parameters = [token[1:-1] for token in re.findall(r"\([a-zA-Z,]+\)", statement)]
        flattened: List[str] = []
        for token in parameters:
            flattened.extend(filter(None, token.split(",")))
        lowercase_params = [p for p in flattened if p.islower()]
        seen: Dict[str, None] = {}
        ordered: List[str] = []
        for param in lowercase_params:
            if param not in seen:
                seen[param] = None
                ordered.append(param)
        for para in ordered:
            variable_dict[para] = give_constant(STANDARD_VARIABLE_COUNT, False)
            STANDARD_VARIABLE_COUNT += 1
        predicate_list: List[str] = []
        for predicate in filter(None, statement.split("|")):
            parts = predicate.split("(")
            args = parts[1][:-1].split(",") if len(parts) > 1 else []
            args = [variable_dict.get(arg, arg) for arg in args]
            predicate_list.append(parts[0] + "(" + ",".join(args) + ")")
        standardized.append("|".join(predicate_list))
    return standardized


def prepare_knowledgebase(fol_sentences: Iterable[str]) -> None:
    global PREDICATES_DICT
    for statement in fol_sentences:
        PREDICATES_DICT.clear()
        normalized, mapping = replace_predicate_by_constant(statement)
        PREDICATES_DICT.update(mapping)
        postfix = convert_to_postfix(normalized)
        root = convert_postfix_to_tree(postfix)
        remove_implication(root)
        propagate_negation(root)
        distribute_and_over_or(root)
        inorder = inorder_traversal(root)
        restored = replace_constant_by_predicate(inorder, PREDICATES_DICT)
        statements = restored.split("&")
        statements = standardize_variables(statements)
        for cnf_stmt in statements:
            stmt_obj = Statement(cnf_stmt)
            stmt_obj.add_statement_to_kb(KNOWLEDGE_BASE, KNOWLEDGE_BASE_HASH)


def fol_resolution(
    kb: Set[Statement], kb_hash: Dict[str, Set[Statement]], query: Statement
) -> bool:
    kb2 = set()
    temp_hash: Dict[str, Set[Statement]] = {}
    query.add_statement_to_kb(kb2, temp_hash)
    query.add_statement_to_kb(kb, temp_hash)
    while True:
        history: Dict[str, Set[str]] = {}
        new_statements: Set[Statement] = set()
        if len(kb) > KILL_LIMIT:
            return False
        for statement1 in kb:
            resolving_clauses = statement1.get_resolving_clauses(temp_hash)
            for statement2 in resolving_clauses:
                if statement1 == statement2:
                    continue
                skip = False
                if statement2.statement_string in history:
                    if (
                        statement1.statement_string
                        in history[statement2.statement_string]
                    ):
                        history[statement2.statement_string].discard(
                            statement1.statement_string
                        )
                        skip = True
                if skip:
                    continue
                if (
                    statement1.statement_string in history
                    and statement2.statement_string
                    in history[statement1.statement_string]
                ):
                    history[statement1.statement_string].discard(
                        statement2.statement_string
                    )
                    continue
                history.setdefault(statement1.statement_string, set()).add(
                    statement2.statement_string
                )
                resolvents = statement1.resolve(statement2)
                if resolvents is False:
                    return True
                new_statements |= resolvents
        if new_statements.issubset(kb):
            return False
        new_statements = new_statements.difference(kb)
        kb2 = set()
        temp_hash = {}
        for stmt in new_statements:
            stmt.add_statement_to_kb(kb2, temp_hash)
        kb |= new_statements


def write_results(path: Path, results: Sequence[bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write((TRUE if result else FALSE) + "\n")


def load_problem(path: Path) -> tuple[List[str], List[str]]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    idx = 0
    num_queries = int(lines[idx].strip())
    idx += 1
    queries = [
        lines[idx + i].strip().replace(" ", "").replace("\t", "")
        for i in range(num_queries)
    ]
    idx += num_queries
    num_sentences = int(lines[idx].strip())
    idx += 1
    sentences = [
        lines[idx + i].strip().replace(" ", "").replace("\t", "")
        for i in range(num_sentences)
    ]
    return queries, list(dict.fromkeys(sentences))


def run_resolution(queries: Sequence[str], fol_sentences: Sequence[str]) -> List[bool]:
    reset_state()
    clean_sentences = [
        sentence.replace(" ", "").replace("\t", "") for sentence in fol_sentences
    ]
    prepare_knowledgebase(clean_sentences)
    results: List[bool] = []
    for query_text in queries:
        predicate = Predicate(query_text.replace(" ", "").replace("\t", ""))
        predicate.negate()
        query_statement = Statement(predicate.predicate_string)
        kb = copy.deepcopy(KNOWLEDGE_BASE)
        kb_hash = copy.deepcopy(KNOWLEDGE_BASE_HASH)
        results.append(fol_resolution(kb, kb_hash, query_statement))
    return results


def run_resolution_from_file(input_path: Path, output_path: Path) -> List[bool]:
    queries, sentences = load_problem(input_path)
    results = run_resolution(queries, sentences)
    write_results(output_path, results)
    return results


def factor_statements(statement_set: Iterable[Statement]) -> Iterable[Statement]:
    for statement in statement_set:
        if statement.predicate_set is None:
            continue
        predicate_list = list(statement.predicate_set)
        for index, predicate1 in enumerate(predicate_list):
            for predicate2 in predicate_list[index + 1 :]:
                if predicate1.negative == predicate2.negative:
                    substitution = predicate1.unify_with_predicate(predicate2)
                    if substitution is False:
                        continue
                    for pred in predicate_list:
                        pred.substitute(substitution)
        statement.init_from_predicate_set(set(predicate_list))
    return statement_set
