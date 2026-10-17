"""Skill-level evaluation on top of skills.txt data.

Layer 1 (numbers) = skills.txt row.
Layer 2 (this module) = calc tokens + level-band formulas.
Layer 3 (srvdofunc behaviour: always-hit, weapon-damage use, pipeline order)
is NOT here — it is hard-coded in the game executable and must be authored
separately with sources.

Token semantics are tagged:
  CONFIRMED  - documented / standard community definition
  ASSUMED    - inferred from naming + usage; see TOKEN_STATUS
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .calc import UnsupportedToken, evaluate, parse

# ----------------------------------------------------------------- data
EXPR_COLUMNS = (
    [f"calc{i}" for i in range(1, 11)]
    + [f"aurastatcalc{i}" for i in range(1, 7)]
    + [f"passivecalc{i}" for i in range(1, 15)]
    + ["auralencalc", "aurarangecalc", "ToHitCalc",
       "DmgSymPerCalc", "EDmgSymPerCalc", "ELenSymPerCalc"]
)


def _num(v, default=0) -> int:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v == "":
        return default
    return int(float(v))


class SkillDB:
    def __init__(self, df: pd.DataFrame):
        df = df[df["skill"].notna()].copy()
        self.df = df
        self.rows = {r["skill"]: r for _, r in df.iterrows()}

    @classmethod
    def load(cls, path: str | Path) -> "SkillDB":
        path = Path(path)
        sep = "\t" if path.suffix.lower() == ".txt" else ","
        return cls(pd.read_csv(path, sep=sep, low_memory=False))

    def __getitem__(self, name: str):
        return self.rows[name]

    def by_class(self, cls_code: str) -> list[str]:
        return self.df[self.df["charclass"] == cls_code]["skill"].tolist()


# ------------------------------------------------------- level formulas
def level_bands5(lvl: int) -> tuple[int, int, int, int, int]:
    """Number of levels falling in each band: 2-8, 9-16, 17-22, 23-28, 29+."""
    c = lambda x, hi: max(0, min(x, hi))  # noqa: E731
    return (c(lvl - 1, 7), c(lvl - 8, 8), c(lvl - 16, 6), c(lvl - 22, 6), max(0, lvl - 28))


def level_bands3(lvl: int) -> tuple[int, int, int]:
    """Bands used by ELevLen1..3: 2-8, 9-16, 17+."""
    c = lambda x, hi: max(0, min(x, hi))  # noqa: E731
    return (c(lvl - 1, 7), c(lvl - 8, 8), max(0, lvl - 16))


def level_formula(base: int, incs: list[int], lvl: int) -> int:
    """'Level Damage Formula' from the D2R data guide (5 increment params)."""
    if lvl <= 0:
        return 0
    if len(incs) == 5:
        bands = level_bands5(lvl)
    elif len(incs) == 3:
        bands = level_bands3(lvl)
    else:
        raise ValueError("need 3 or 5 increments")
    return base + sum(b * i for b, i in zip(bands, incs))


def dm(lvl: int, lo: int, hi: int) -> int:
    """Diminishing returns: lo + (hi-lo) * floor(110*lvl/(lvl+6)) / 100."""
    if lvl <= 0:
        return 0
    return lo + (hi - lo) * ((110 * lvl) // (lvl + 6)) // 100


def ln(lvl: int, base: int, per: int) -> int:
    """Linear: base + (lvl-1)*per."""
    return base + (lvl - 1) * per


# digits in lnXY/dmXY -> param index. '91' is ambiguous (par9+par10 assumed).
_PAIR = {"12": (1, 2), "21": (2, 1), "34": (3, 4), "43": (4, 3),
         "56": (5, 6), "65": (6, 5), "78": (7, 8), "87": (8, 7),
         "91": (9, 10)}

TOKEN_STATUS = {
    "lvl": "CONFIRMED  effective skill level (hard + bonuses)",
    "blvl": "CONFIRMED  base level (hard points only); used for synergies",
    "ulvl": "CONFIRMED  unit (character) level",
    "parN/paNN": "CONFIRMED  ParamN column",
    "lnXY": "CONFIRMED  parX + (lvl-1)*parY",
    "dmXY": "CONFIRMED  parX + (parY-parX)*floor(110*lvl/(lvl+6))/100",
    "ln91/dm91": "ASSUMED   par9,par10 (not used by paladin)",
    "toht": "CONFIRMED  ToHit + (lvl-1)*LevToHit",
    "edmn/edmx": "ASSUMED   elem min/max, points, no synergy (pal: no synergy rows, moot)",
    "edns": "ASSUMED   = edmn (pal: Prayer only, HitShift 8, no synergy, moot)",
    "enms/exms": "ASSUMED   elem min/max incl. synergy, in 1/256 units (fits '*par5/256' usage)",
    "edln": "ASSUMED   elem length in frames",
}


# ------------------------------------------------------------ evaluator
@dataclass
class Character:
    hard: dict[str, int] = field(default_factory=dict)  # hard points per skill
    plus_skills: int = 0                                  # +all / +class / +tree, merged
    level: int = 90

    def blvl(self, s: str) -> int:
        return self.hard.get(s, 0)

    def lvl(self, s: str) -> int:
        h = self.blvl(s)
        return h + self.plus_skills if h > 0 else 0


class SkillEvaluator:
    def __init__(self, db: SkillDB, char: Character | None = None):
        self.db = db
        self.char = char or Character()

    # -- primitive token resolution for skill `name` at (lvl, blvl)
    def token(self, name: str, tok: str, lvl: int, blvl: int) -> int:
        r = self.db[name]
        p = lambda i: _num(r.get(f"Param{i}"))  # noqa: E731
        if tok == "lvl":
            return lvl
        if tok == "blvl":
            return blvl
        if tok == "ulvl":
            return self.char.level
        if tok.startswith("par") and tok[3:].isdigit():
            return p(int(tok[3:]))
        if tok.startswith("pa") and tok[2:].isdigit():
            return p(int(tok[2:]))
        if tok[:2] in ("ln", "dm") and tok[2:] in _PAIR:
            a, b = _PAIR[tok[2:]]
            return ln(lvl, p(a), p(b)) if tok[:2] == "ln" else dm(lvl, p(a), p(b))
        if tok == "toht":
            return ln(lvl, _num(r.get("ToHit")), _num(r.get("LevToHit")))
        if tok in ("edmn", "edns"):
            return self.elem_damage(name, lvl, synergy=False)[1]
        if tok == "edmx":
            return self.elem_damage(name, lvl, synergy=False)[2]
        if tok in ("enms", "exms"):
            _, lo256, hi256 = self.elem_damage(name, lvl, synergy=True, units256=True)
            return lo256 if tok == "enms" else hi256
        if tok == "edln":
            return self.elem_length(name, lvl)
        raise UnsupportedToken(tok)

    def expr(self, name: str, src: str, lvl: int | None = None, blvl: int | None = None) -> int:
        lvl = self.char.lvl(name) if lvl is None else lvl
        blvl = self.char.blvl(name) if blvl is None else blvl
        node = parse(src)
        return evaluate(
            node,
            resolve=lambda t: self.token(name, t, lvl, blvl),
            skill_ref=lambda s, attr: self._ref(s, attr),
        )

    def _ref(self, other: str, attr: str) -> int:
        lvl, blvl = self.char.lvl(other), self.char.blvl(other)
        return self.token(other, attr, lvl, blvl)

    def column(self, name: str, col: str, lvl: int | None = None) -> int | None:
        v = self.db[name].get(col)
        if v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() == "":
            return None
        return self.expr(name, str(v), lvl, lvl if lvl is not None else None)

    # -- level-band damage
    def _synergy(self, name: str, col: str) -> int:
        v = self.db[name].get(col)
        if not isinstance(v, str) or not v.strip():
            return 0
        return self.expr(name, v)

    def phys_damage(self, name: str, lvl: int, synergy: bool = True) -> tuple[int, int]:
        r = self.db[name]
        hs = _num(r.get("HitShift"), 8)
        lo = level_formula(_num(r.get("MinDam")), [_num(r.get(f"MinLevDam{i}")) for i in range(1, 6)], lvl)
        hi = level_formula(_num(r.get("MaxDam")), [_num(r.get(f"MaxLevDam{i}")) for i in range(1, 6)], lvl)
        syn = self._synergy(name, "DmgSymPerCalc") if synergy else 0
        f = lambda v: ((v << hs) * (100 + syn) // 100) >> 8  # noqa: E731
        return f(lo), f(hi)

    def elem_damage(self, name: str, lvl: int, synergy: bool = True, units256: bool = False):
        r = self.db[name]
        hs = _num(r.get("HitShift"), 8)
        et = r.get("EType") if isinstance(r.get("EType"), str) else None
        lo = level_formula(_num(r.get("EMin")), [_num(r.get(f"EMinLev{i}")) for i in range(1, 6)], lvl)
        hi = level_formula(_num(r.get("EMax")), [_num(r.get(f"EMaxLev{i}")) for i in range(1, 6)], lvl)
        syn = self._synergy(name, "EDmgSymPerCalc") if synergy else 0
        lo, hi = ((v << hs) * (100 + syn) // 100 for v in (lo, hi))
        if units256:
            return et, lo, hi
        return et, lo >> 8, hi >> 8

    def elem_length(self, name: str, lvl: int) -> int:
        r = self.db[name]
        return level_formula(_num(r.get("ELen")), [_num(r.get(f"ELevLen{i}")) for i in range(1, 4)], lvl)
