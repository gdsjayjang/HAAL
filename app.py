"""D2R Smite 전투 시뮬레이터 — Streamlit (thin end-to-end prototype).

엔진이 계산하는 값: Smite 데미지%, Holy Shield Smite 데미지, Fanaticism 데미지%/공속%
직접 입력하는 값: 아직 엔진에 없는 층(아이템·프레임·몬스터)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from d2r.sim import ASSUMPTIONS, FPS, Setup, Target, expected_dps, hit_range, simulate
from d2r.skill import SkillDB

COLORS = {"A": "#2a78d6", "B": "#eb6834"}
BANDS = {"A": "rgba(42,120,214,0.18)", "B": "rgba(235,104,52,0.18)"}

st.set_page_config(page_title="D2R Smite Simulator", page_icon="⚔️", layout="wide")


@st.cache_resource
def load_db():
    root = Path(__file__).parent / "data"
    for name in ("skills.txt", "skills.csv"):
        if (root / name).exists():
            return SkillDB.load(root / name)
    st.error("data/skills.txt 또는 data/skills.csv 가 없습니다.")
    st.stop()


db = load_db()

DEFAULTS = {
    "A": dict(weapon=(380, 440), shield=(40, 70), extra=0, ds=50, cb=0, frames=7),
    "B": dict(weapon=(300, 360), shield=(40, 70), extra=0, ds=20, cb=35, frames=7),
}


def setup_inputs(key: str) -> Setup:
    d = DEFAULTS[key]
    st.markdown("**스킬 레벨** · 엔진 계산")
    c1, c2, c3 = st.columns(3)
    smite = c1.number_input("Smite", 0, 60, 26, key=f"{key}_sm")
    hs = c2.number_input("Holy Shield", 0, 60, 26, key=f"{key}_hs")
    fan = c3.number_input("Fanaticism", 0, 60, 26, key=f"{key}_fa")
    st.markdown("**장비** · 직접 입력 (Item Engine 전)")
    use_w = st.checkbox("무기 데미지 포함", True, key=f"{key}_uw",
                        help="Smite가 무기 데미지를 쓰는지는 srvdofunc 150 검증 전입니다.")
    c1, c2 = st.columns(2)
    wmin = c1.number_input("무기 min", 0, 5000, d["weapon"][0], key=f"{key}_wmin", disabled=not use_w)
    wmax = c2.number_input("무기 max", 0, 5000, d["weapon"][1], key=f"{key}_wmax", disabled=not use_w)
    smin = c1.number_input("방패 Smite min", 0, 2000, d["shield"][0], key=f"{key}_smin")
    smax = c2.number_input("방패 Smite max", 0, 2000, d["shield"][1], key=f"{key}_smax")
    extra = st.number_input("기타 데미지 % (가산)", 0, 2000, d["extra"], key=f"{key}_ex")
    c1, c2, c3 = st.columns(3)
    ds = c1.number_input("DS %", 0, 100, d["ds"], key=f"{key}_ds")
    cb = c2.number_input("CB %", 0, 100, d["cb"], key=f"{key}_cb")
    frames = c3.number_input("공격 프레임", 3, 30, d["frames"], key=f"{key}_fr",
                             help="IAS 브레이크포인트 결과 프레임. animdata 구현 전까지 직접 입력.")
    return Setup(name=key, smite_lvl=smite, holy_shield_lvl=hs, fanaticism_lvl=fan,
                 weapon_min=wmin, weapon_max=max(wmin, wmax), use_weapon=use_w,
                 shield_min=smin, shield_max=max(smin, smax), extra_dmg_pct=extra,
                 ds_pct=ds, cb_pct=cb, frames=frames)


# ------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("대상 몬스터")
    st.caption("Monster Engine 전 · 직접 입력 (예시값)")
    hp = st.number_input("HP", 1000, 10_000_000, 100_000, step=1000)
    res = st.number_input("물리 저항 %", -100, 100, 0)
    cbf = st.number_input("CB 비율 (현재 HP 대비 %)", 0.0, 100.0, 12.5, step=0.5,
                          help="보스 대상 CB 비율. 미검증 가정값입니다.") / 100
    st.divider()
    n_runs = st.select_slider("시뮬레이션 횟수", [200, 500, 1000, 2000, 5000], 2000)
    compare = st.toggle("세팅 B와 비교", True)

target = Target(hp=int(hp), phys_res=int(res), cb_fraction=cbf)

st.title("D2R Smite 전투 시뮬레이터")
st.caption("엔진 계산값과 직접 입력값을 섞은 프로토타입입니다. 입력칸은 엔진이 완성되는 대로 계산값으로 대체됩니다.")

keys = ["A", "B"] if compare else ["A"]
cols = st.columns(len(keys))
setups = {}
for k, c in zip(keys, cols):
    with c.expander(f"세팅 {k}", expanded=True):
        setups[k] = setup_inputs(k)

# ------------------------------------------------------------- run
results = {}
for k, s in setups.items():
    lo, hi, d = hit_range(db, s)
    times, H, ttk = simulate(lo, hi, s, target, n=n_runs, seed=42)
    results[k] = dict(lo=lo, hi=hi, d=d, times=times, H=H, ttk=ttk, dps=expected_dps(lo, hi, s, target))

# ------------------------------------------------------------- metrics
st.subheader("결과")
mcols = st.columns(len(keys))
for k, c in zip(keys, mcols):
    r, s = results[k], setups[k]
    finite = r["ttk"][np.isfinite(r["ttk"])]
    med = float(np.median(finite)) if len(finite) else float("inf")
    other = [x for x in keys if x != k]
    delta = None
    if other:
        of = results[other[0]]["ttk"]
        of = of[np.isfinite(of)]
        if len(of) and len(finite):
            delta = f"{med - float(np.median(of)):+.2f}s vs {other[0]}"
    with c:
        st.markdown(f"#### 세팅 {k}")
        a, b, cc = st.columns(3)
        a.metric("평균 1회 데미지", f"{(r['lo'] + r['hi']) // 2:,}")
        b.metric("기대 DPS (CB 제외)", f"{r['dps']:,.0f}")
        cc.metric("TTK 중앙값", f"{med:.2f}s", delta, delta_color="inverse")
        if len(finite):
            p10, p90 = np.percentile(finite, [10, 90])
            st.caption(f"1회 {r['lo']:,}–{r['hi']:,} · TTK 10–90%: {p10:.2f}s – {p90:.2f}s · 공격 {FPS / s.frames:.2f}회/초 · "
                       f"미처치 {len(r['ttk']) - len(finite)}회")

# ------------------------------------------------------------- HP timeline
st.subheader("대상 HP 변화")
fig = go.Figure()
for k in keys:
    r = results[k]
    pct = r["H"] / target.hp * 100
    p10, p50, p90 = np.percentile(pct, [10, 50, 90], axis=0)
    t = r["times"]
    fig.add_trace(go.Scatter(x=np.r_[t, t[::-1]], y=np.r_[p90, p10[::-1]], fill="toself",
                             fillcolor=BANDS[k], line=dict(width=0), hoverinfo="skip",
                             name=f"{k} 10–90%", showlegend=True))
    fig.add_trace(go.Scatter(x=t, y=p50, mode="lines", line=dict(color=COLORS[k], width=2, shape="hv"),
                             name=f"{k} 중앙값", hovertemplate="%{x:.2f}s · HP %{y:.1f}%<extra>" + k + "</extra>"))
fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                  xaxis_title="시간 (초)", yaxis_title="HP %", yaxis_range=[0, 102],
                  legend=dict(orientation="h", y=1.08, x=0))
st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------- TTK distribution
st.subheader("TTK 분포")
fig2 = go.Figure()
for k in keys:
    f = results[k]["ttk"]
    f = f[np.isfinite(f)]
    fig2.add_trace(go.Histogram(x=f, name=f"세팅 {k}", marker_color=COLORS[k], opacity=0.65,
                                xbins=dict(size=setups[k].frames / FPS),
                                hovertemplate="%{x:.2f}s · %{y}회<extra>" + k + "</extra>"))
fig2.update_layout(barmode="overlay", height=300, margin=dict(l=10, r=10, t=10, b=10),
                   xaxis_title="TTK (초)", yaxis_title="시뮬레이션 횟수",
                   legend=dict(orientation="h", y=1.1, x=0))
st.plotly_chart(fig2, width="stretch")

# ------------------------------------------------------------- transparency
with st.expander("엔진 계산값 (skills 데이터 기반)"):
    rows = []
    for k in keys:
        d, s = results[k]["d"], setups[k]
        rows.append({"세팅": k, "Smite %": d["smite_pct"],
                     "Holy Shield Smite 데미지": f"{d['hs_min']}–{d['hs_max']}",
                     "Fanaticism 데미지 %": d["fan_dmg_pct"], "Fanaticism 공속 %": d["fan_ias"],
                     "총 데미지 배수 %": d["mult_pct"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Fanaticism 공속 %는 참고용입니다. 프레임 변환(animdata)은 아직 구현되지 않아 공격 프레임은 직접 입력합니다.")

with st.expander("계산 가정 (미검증 항목 포함)"):
    for a in ASSUMPTIONS:
        st.markdown(f"- {a}")
