# Horadric Artificial Analytics Lab

```
conda create -n d2r python=3.12 -y
pip install -r requirements.txt
```


```
d2r/calc.py      토크나이저 · 파서(AST) · 정수 평가기 (C식 나눗셈)
d2r/skill.py     토큰 의미(ln/dm/par/toht/elem…), Level Damage Formula, HitShift, 시너지
tests/           pytest (데이터 경로: data/skills.csv 또는 $D2R_SKILLS)
scripts/make_level_table.py   클래스별 Lv1~N 전 수식 표(xlsx)
```

```bash

python -m pytest -q
python scripts/make_level_table.py data/skills.csv pal paladin_skill_levels.xlsx 30
```

```python
from d2r.skill import SkillDB, SkillEvaluator, Character
db = SkillDB.load("data/skills.csv")          # .txt(탭)도 가능
e = SkillEvaluator(db, Character(hard={"Holy Shield": 20, "Defiance": 20}, plus_skills=6))
e.column("Holy Shield", "calc1")               # Armor % (Defiance 시너지 포함)
e.phys_damage("Holy Shield", e.char.lvl("Holy Shield"))
```

범위 밖(Layer 3, 실행파일 하드코딩): srvdofunc별 동작 — Smite 필중, 무기/방패 데미지 합산,
데미지 파이프라인 순서. 토큰 확신도는 `TOKEN_STATUS` 참조.
