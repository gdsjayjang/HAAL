"""Monte Carlo battle simulation (Layer 7, thin version).

Damage model for Smite is a PLACEHOLDER for Layer 3 (srvdofunc 150) and is
listed in ASSUMPTIONS; every number the engine cannot compute yet is an input.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .skill import Character, SkillDB, SkillEvaluator

FPS = 25

ASSUMPTIONS = [
    "Smite 1회 기본 데미지 = 무기 데미지(토글) + 방패 Smite 데미지 + Holy Shield Smite 데미지 — srvdofunc 150 미검증",
    "데미지 배수 = 100% + Smite% + Fanaticism 본인 데미지% + 기타 데미지% (모두 가산) — 합산 방식 미검증",
    "Deadly Strike: 발동 시 물리 데미지 ×2",
    "Crushing Blow: 발동 시 대상 '현재' HP × CB 비율만큼 추가 감소, 일반 데미지보다 먼저 적용 — 비율·순서 미검증",
    "물리 저항은 최종 데미지에 (100-저항)% 곱",
    "공격 간격 = 입력한 프레임 / 25fps (animdata 미구현)",
    "명중률: Smite는 필중(기본 100%)",
    "Open Wounds, 원소 데미지, 생명력 회복, 플레이어 수 보정은 미반영",
]


@dataclass
class Setup:
    name: str
    smite_lvl: int = 20
    holy_shield_lvl: int = 20
    fanaticism_lvl: int = 20
    weapon_min: int = 0
    weapon_max: int = 0
    use_weapon: bool = True
    shield_min: int = 0
    shield_max: int = 0
    extra_dmg_pct: int = 0
    ds_pct: float = 0.0
    cb_pct: float = 0.0
    frames: int = 7
    hit_pct: float = 100.0


@dataclass
class Target:
    name: str = "Diablo"
    hp: int = 100_000
    phys_res: int = 0
    cb_fraction: float = 0.125


def derive(db: SkillDB, s: Setup) -> dict:
    """Values the engine computes from skills data."""
    hard = {"Smite": s.smite_lvl, "Holy Shield": s.holy_shield_lvl, "Fanaticism": s.fanaticism_lvl}
    e = SkillEvaluator(db, Character(hard={k: v for k, v in hard.items() if v > 0}))
    smite_pct = e.column("Smite", "calc1", s.smite_lvl) if s.smite_lvl else 0
    hs_min, hs_max = e.phys_damage("Holy Shield", s.holy_shield_lvl) if s.holy_shield_lvl else (0, 0)
    fan_dmg = e.column("Fanaticism", "passivecalc1", s.fanaticism_lvl) if s.fanaticism_lvl else 0
    fan_ias = e.column("Fanaticism", "aurastatcalc1", s.fanaticism_lvl) if s.fanaticism_lvl else 0
    return dict(smite_pct=smite_pct, hs_min=hs_min, hs_max=hs_max, fan_dmg_pct=fan_dmg, fan_ias=fan_ias)


def hit_range(db: SkillDB, s: Setup) -> tuple[int, int, dict]:
    d = derive(db, s)
    w_lo, w_hi = (s.weapon_min, s.weapon_max) if s.use_weapon else (0, 0)
    lo = w_lo + s.shield_min + d["hs_min"]
    hi = w_hi + s.shield_max + d["hs_max"]
    mult = 100 + d["smite_pct"] + d["fan_dmg_pct"] + s.extra_dmg_pct
    d["mult_pct"] = mult
    return lo * mult // 100, hi * mult // 100, d


def expected_dps(lo: int, hi: int, s: Setup, t: Target) -> float:
    """Mean DPS excluding Crushing Blow (CB depends on remaining HP)."""
    mean = (lo + hi) / 2 * (1 + s.ds_pct / 100) * (100 - t.phys_res) / 100
    return mean * (s.hit_pct / 100) * FPS / s.frames


def simulate(lo: int, hi: int, s: Setup, t: Target, n: int = 2000,
             max_attacks: int = 20000, seed: int = 0):
    """Returns (attack_times [K], hp matrix [n, K+1] incl. t=0, ttk [n] seconds; inf if alive)."""
    rng = np.random.default_rng(seed)
    hp = np.full(n, float(t.hp))
    hist = [hp.copy()]
    ttk = np.full(n, np.inf)
    period = s.frames / FPS
    for k in range(1, max_attacks + 1):
        alive = hp > 0
        if not alive.any():
            break
        hit = rng.random(n) < s.hit_pct / 100
        cb = hit & (rng.random(n) < s.cb_pct / 100)
        hp = np.where(alive & cb, hp - np.floor(hp * t.cb_fraction), hp)
        dmg = rng.integers(lo, hi + 1, size=n).astype(float) if hi >= lo else np.zeros(n)
        ds = rng.random(n) < s.ds_pct / 100
        dmg = np.where(ds, dmg * 2, dmg)
        dmg = np.floor(dmg * (100 - t.phys_res) / 100)
        hp = np.where(alive & hit, hp - dmg, hp)
        hp = np.maximum(hp, 0)
        newly = alive & (hp <= 0)
        ttk[newly] = k * period
        hist.append(hp.copy())
    H = np.stack(hist, axis=1)
    times = np.arange(H.shape[1]) * period
    return times, H, ttk
