from dataclasses import dataclass
from d2r.skill import SkillDB, SkillEvaluator

@dataclass
class Smite:
    shield_min: int
    shiled_max: int
    strength: int

    smite_level: int
    holy_shiled_level: int
    fanaticism_level:int

    flat_damage: int = 0
    off_weapon_ed: int = 0

    holy_shiled_active: bool = True
    fanaticism_active: bool = True

def calc_smite(db: SkillDB, build: Smite):
    evaluator = SkillEvaluator(db)

    # 1. Smite 스킬 ED%
    smite_ed = (
        evaluator.column('Smite', 'calc1', build.smite_level)
        if build.smite_level > 0 else 0
    ) or 0

    # 2. Holy Shield 추가 데미지
    if build.holy_shield_active and build.holy_shiled_level > 0:
        hs_min, hs_max = evaluator.phys_damage(
            'Holy Shield', build.holy_shiled_level
        )
    else:
        hs_min, hs_max = 0, 0

    # 3. Fanaticism 본인 ED%
    fana_ed = (
        evaluator.column(
            'Fanaticism',
            'passivecalc1',
            build.fanaticism_level
        )
        if build.fanaticism_active and build.fanaticism_level > 0
        else 0
    ) or 0

    # 4. 기본 데미지
    base_min = build.shield_min + hs_min + build.flat_damage
    base_max = build.shield_max + hs_max + build.flat_damage

    # 5. ED% 합산
    total_ed = (
        build.strength
        + smite_ed
        + fana_ed
        + build.off_weapon_ed
    )

    # 6. 최종 데미지
    multiplier = 100 + total_ed
    damage_min = base_min * multiplier // 100
    damage_max = base_max * multiplier // 100

    return {
        'base_min': base_min,
        'base_max': base_max,
        'smite_ed': smite_ed,
        'fanaticism_ed': fana_ed,
        'total_ed': total_ed,
        'damage_min': damage_min,
        'damage_max': damage_max,
        'damage_avg': (damage_min + damage_max) / 2,
    }

if __name__ == "__main__":
    db = SkillDB.load("data/skills.txt")

    build = Smite(
        shield_min=22,
        shield_max=70,
        strength=150,
        smite_level=20,
        holy_shield_level=20,
        fanaticism_level=20,
        flat_damage=400,
    )

    result = calc_smite(db, build)

    for key, value in result.items():
        print(f"{key}: {value}")