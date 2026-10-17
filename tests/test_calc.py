import os
from pathlib import Path

import pytest

from d2r.calc import cdiv, evaluate, parse
from d2r.skill import Character, SkillDB, SkillEvaluator, dm, level_formula

DATA = Path(os.environ.get("D2R_SKILLS", Path(__file__).parents[1] / "data" / "skills.csv"))


def ev(src, env=None, refs=None):
    env = env or {}
    return evaluate(parse(src), env.__getitem__, lambda s, a: (refs or {})[(s, a)])


# ---------------- parser / arithmetic
def test_c_division_truncates_toward_zero():
    assert cdiv(7, 2) == 3 and cdiv(-7, 2) == -3


def test_precedence_and_ternary():
    assert ev("1+2*3") == 7
    assert ev("((lvl < 5) ? 0 : ((lvl-4) * 6))", {"lvl": 4}) == 0
    assert ev("((lvl < 5) ? 0 : ((lvl-4) * 6))", {"lvl": 20}) == 96
    assert ev("-min(x,150)", {"x": 200}) == -150
    assert ev("max(6, 8-20/3)") == 6


def test_skill_ref():
    assert ev("ln34+skill('Defiance'.blvl)*15", {"ln34": 10}, {("Defiance", "blvl"): 2}) == 40


# ---------------- formulas
def test_dm_endpoints():
    assert dm(1, 10, 40) == 10 + 30 * 15 // 100        # 110*1/7 = 15
    assert dm(1000, 10, 40) == 10 + 30 * 109 // 100    # approaches lo+1.09*(hi-lo)


def test_level_formula_bands():
    # Holy Shield smite damage min: base 3, +2/+3/+4/+4/+4
    incs = [2, 3, 4, 4, 4]
    assert level_formula(3, incs, 1) == 3
    assert level_formula(3, incs, 8) == 3 + 7 * 2
    assert level_formula(3, incs, 20) == 3 + 7 * 2 + 8 * 3 + 4 * 4


# ---------------- against real data
@pytest.fixture(scope="module")
def db():
    if not DATA.exists():
        pytest.skip(f"skills data not found: {DATA}")
    return SkillDB.load(DATA)


def at(db, skill, lvl, **hard):
    hard = {skill: lvl, **{k.replace("_", " "): v for k, v in hard.items()}}
    return SkillEvaluator(db, Character(hard=hard))


def test_smite_damage_percent(db):
    for L in (1, 20, 30):
        assert at(db, "Smite", L).column("Smite", "calc1") == 15 + 15 * (L - 1)


def test_fanaticism_attack_speed_dm(db):
    # dm34: 10 -> 40
    assert at(db, "Fanaticism", 20).column("Fanaticism", "aurastatcalc1") == 10 + 30 * (2200 // 26) // 100


def test_holy_shield_synergy_from_defiance(db):
    e = at(db, "Holy Shield", 20, Defiance=20)
    base = at(db, "Holy Shield", 20).column("Holy Shield", "calc1")
    assert e.column("Holy Shield", "calc1") == base + 20 * 15


def test_zeal_hits_and_damage(db):
    e = at(db, "Zeal", 20)
    assert e.column("Zeal", "calc1") == 5          # min(2+20-1, 5)
    assert e.column("Zeal", "calc2") == (20 - 4) * 6


def test_every_paladin_expression_parses_and_evaluates(db):
    from d2r.skill import EXPR_COLUMNS
    for s in db.by_class("pal"):
        e = at(db, s, 20)
        for c in EXPR_COLUMNS:
            if c in db[s] and isinstance(db[s][c], str):
                e.column(s, c, 20)   # must not raise
