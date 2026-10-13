"""Evaluate derived-metric formulas exactly, with Decimal arithmetic.

Formulas are restricted to metric names, numbers, + - * / and parentheses (config.py checks
this); they are parsed with ast and never passed to eval.
"""
import ast
from decimal import Decimal, localcontext

PLACES = Decimal("0.0001")   # derived values are rounded to 4 decimal places


class DeriveError(Exception):
    pass


def evaluate(formula, values):
    """values: name -> Decimal. Returns a Decimal, or None if any input is missing."""
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub)
    bad = [type(n).__name__ for n in ast.walk(ast.parse(formula, mode="eval")) if not isinstance(n, allowed)]
    if bad:
        raise DeriveError(f"formula may only use names, numbers and + - * /: found {sorted(set(bad))}")
    if any(values.get(n) is None for n in names(formula)):
        return None
    with localcontext() as ctx:
        ctx.prec = 34
        result = _eval(ast.parse(formula, mode="eval").body, values)
    return result.quantize(PLACES)


def names(formula):
    return {n.id for n in ast.walk(ast.parse(formula, mode="eval")) if isinstance(n, ast.Name)}


def _eval(node, values):
    if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
        a, b = _eval(node.left, values), _eval(node.right, values)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if b == 0:
            raise DeriveError("division by zero")
        return a / b
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, values)
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    raise DeriveError(f"unsupported expression: {ast.dump(node)}")


def order(metrics):
    """Derived metrics sorted so every input comes before the metric that uses it."""
    done, out = set(), []

    def visit(mid):
        if mid in done:
            return
        for i in metrics[mid].get("inputs") or []:
            if metrics.get(i, {}).get("type") == "derived":
                visit(i)
        done.add(mid)
        out.append(mid)

    for mid, m in metrics.items():
        if m["type"] == "derived":
            visit(mid)
    return out
