"""D2R skills.txt calc-expression interpreter.

Grammar (precedence low -> high):
    expr     := ternary
    ternary  := compare ('?' expr ':' expr)?
    compare  := additive (('<'|'>'|'<='|'>='|'=='|'!=') additive)*
    additive := mult (('+'|'-') mult)*
    mult     := unary (('*'|'/') unary)*
    unary    := '-' unary | primary
    primary  := NUMBER | IDENT | IDENT '(' args ')' | '(' expr ')' | STRING '.' IDENT

All arithmetic is integer; '/' truncates toward zero (C semantics), which is
what the game engine does. Identifier semantics are resolved by an evaluation
context (see d2r.skill.SkillEvaluator), not here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Union

TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<num>\d+)"
    r"|(?P<str>'[^']*')"
    r"|(?P<id>[A-Za-z_][A-Za-z_0-9]*)"
    r"|(?P<op><=|>=|==|!=|[-+*/(),.?:<>])"
    r")"
)


class CalcSyntaxError(ValueError):
    pass


class UnsupportedToken(KeyError):
    """Raised when an identifier has no known semantics in the context."""


def tokenize(src: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    src = src.strip()
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m or m.end() == pos:
            raise CalcSyntaxError(f"bad char at {pos} in {src!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
        while pos < len(src) and src[pos].isspace():
            pos += 1
    out.append(("eof", ""))
    return out


# ---------------- AST ----------------
@dataclass(frozen=True)
class Num:
    v: int


@dataclass(frozen=True)
class Ident:
    name: str


@dataclass(frozen=True)
class SkillRef:  # 'Skill Name'.attr  (only valid as skill()/stat() argument)
    target: str
    attr: str


@dataclass(frozen=True)
class Call:
    fn: str
    args: tuple


@dataclass(frozen=True)
class Unary:
    op: str
    x: "Node"


@dataclass(frozen=True)
class Bin:
    op: str
    a: "Node"
    b: "Node"


@dataclass(frozen=True)
class Tern:
    c: "Node"
    a: "Node"
    b: "Node"


Node = Union[Num, Ident, SkillRef, Call, Unary, Bin, Tern]


class _Parser:
    def __init__(self, src: str):
        self.src = src
        self.t = tokenize(src)
        self.i = 0

    def peek(self):
        return self.t[self.i]

    def take(self, val=None):
        k, v = self.t[self.i]
        if val is not None and v != val:
            raise CalcSyntaxError(f"expected {val!r}, got {v!r} in {self.src!r}")
        self.i += 1
        return k, v

    def parse(self) -> Node:
        n = self.expr()
        if self.peek()[0] != "eof":
            raise CalcSyntaxError(f"trailing {self.peek()[1]!r} in {self.src!r}")
        return n

    def expr(self):
        c = self.compare()
        if self.peek()[1] == "?":
            self.take("?")
            a = self.expr()
            self.take(":")
            b = self.expr()
            return Tern(c, a, b)
        return c

    def compare(self):
        n = self.additive()
        while self.peek()[1] in ("<", ">", "<=", ">=", "==", "!="):
            op = self.take()[1]
            n = Bin(op, n, self.additive())
        return n

    def additive(self):
        n = self.mult()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            n = Bin(op, n, self.mult())
        return n

    def mult(self):
        n = self.unary()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            n = Bin(op, n, self.unary())
        return n

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            return Unary("-", self.unary())
        return self.primary()

    def primary(self):
        k, v = self.take()
        if k == "num":
            return Num(int(v))
        if k == "str":
            self.take(".")
            _, attr = self.take()
            return SkillRef(v[1:-1], attr)
        if k == "id":
            if self.peek()[1] == "(":
                self.take("(")
                args = []
                if self.peek()[1] != ")":
                    args.append(self.expr())
                    while self.peek()[1] == ",":
                        self.take(",")
                        args.append(self.expr())
                self.take(")")
                return Call(v, tuple(args))
            return Ident(v)
        if v == "(":
            n = self.expr()
            self.take(")")
            return n
        raise CalcSyntaxError(f"unexpected {v!r} in {self.src!r}")


_cache: dict[str, Node] = {}


def parse(src: str) -> Node:
    src = str(src).strip()
    if src not in _cache:
        _cache[src] = _Parser(src).parse()
    return _cache[src]


def cdiv(a: int, b: int) -> int:
    """C-style integer division (truncate toward zero)."""
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def evaluate(node: Node, resolve: Callable[[str], int],
             skill_ref: Callable[[str, str], int]) -> int:
    """Evaluate AST. `resolve(name)` gives identifier values; `skill_ref(skill, attr)`
    resolves 'Skill'.attr references."""
    ev = lambda n: evaluate(n, resolve, skill_ref)  # noqa: E731
    if isinstance(node, Num):
        return node.v
    if isinstance(node, Ident):
        return int(resolve(node.name))
    if isinstance(node, Unary):
        return -ev(node.x)
    if isinstance(node, Tern):
        return ev(node.a) if ev(node.c) else ev(node.b)
    if isinstance(node, Bin):
        a, b = ev(node.a), ev(node.b)
        op = node.op
        if op == "+": return a + b
        if op == "-": return a - b
        if op == "*": return a * b
        if op == "/": return cdiv(a, b)
        if op == "<": return int(a < b)
        if op == ">": return int(a > b)
        if op == "<=": return int(a <= b)
        if op == ">=": return int(a >= b)
        if op == "==": return int(a == b)
        if op == "!=": return int(a != b)
    if isinstance(node, Call):
        fn = node.fn
        if fn == "min":
            return min(ev(a) for a in node.args)
        if fn == "max":
            return max(ev(a) for a in node.args)
        if fn == "skill":
            ref = node.args[0]
            if not isinstance(ref, SkillRef):
                raise CalcSyntaxError("skill() expects 'Name'.attr")
            return int(skill_ref(ref.target, ref.attr))
        raise UnsupportedToken(f"function {fn}()")
    if isinstance(node, SkillRef):
        raise CalcSyntaxError("bare 'Name'.attr outside skill()")
    raise CalcSyntaxError(f"unknown node {node!r}")
