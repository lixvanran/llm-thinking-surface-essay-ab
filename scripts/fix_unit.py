#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ fix_unit.py —— ★ 补跑【解析器故障】导致中断的单元 ★

★ 场景（★ 实测 2026-10-29 ★）：★ A1×T2×rep2 的【选轴】输出其实完全可用（★ 只少一个右括号 ★），
★   ★ 但当时的解析器判它失败 ⇒ 该单元没往下跑。★★
★ ★ 处置：★ **复用原来那次的轴输出**（★ 不重新生成、★ 不重新付费 ★）★ 只补【分支 ×4 ＋ 合流】★
★   ⇒ ★ 这不是「因为结果不好重跑」★ ——★ 是修工具后把没跑完的跑完、★ 且不改变任何已有读数 ★★
"""
import concurrent.futures as cf, importlib.util, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("r", ROOT / "scripts" / "runner.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

ARM, TID, REP = sys.argv[1], sys.argv[2], int(sys.argv[3])
gold = json.loads((ROOT / "gold" / "gold_axes.json").read_text(encoding="utf-8"))

ax_txt = (R.TXT / ("%s__%s__r%d__axes.md" % (ARM, TID, REP))).read_text(encoding="utf-8")
axes = R.parse_axes(ax_txt)
assert axes, "★ 仍然解析不出轴"
axes = axes[:R.N_BRANCH]
while len(axes) < R.N_BRANCH:
    axes.append(dict(axes[-1], id="dup"))
print("★ 复用原轴（%d 条）: %s" % (len(axes), [a["name"] for a in axes]))

t0 = time.time()
branches = []
with cf.ThreadPoolExecutor(max_workers=R.N_BRANCH) as ex:
    futs = [ex.submit(R.call, ARM, TID, REP, "branch%d" % (k + 1),
                      R.prompt_branch(ARM, gold, TID, axes[k], k + 1), max_tokens=4500)
            for k in range(R.N_BRANCH)]
    for f in futs:
        b, _ = f.result()
        branches.append(b)
print("★ 分支字数: %s" % [len(b) for b in branches])
assert all(branches), "★ 分支有失败"
mg, _ = R.call(ARM, TID, REP, "merge", R.prompt_merge(ARM, gold, TID, branches, axes), max_tokens=5000)
assert mg, "★ 合流失败"
print("★ 合流 %d 字 ｜ 总耗时 %.0fs" % (len(mg), time.time() - t0))

# ★ 合并进 units.json（★ 只替换这一个单元 ★）
units_p = ROOT / "out" / "units.json"
units = json.loads(units_p.read_text(encoding="utf-8"))
newu = {"arm": ARM, "topic": TID, "rep": REP, "ok": True, "final_chars": len(mg),
        "n_axes": len(axes), "axes_names": [a["name"] for a in axes],
        "stages": ["axes", "branch", "merge"], "wall_s": round(time.time() - t0, 1),
        "n_calls": 5 + R.N_BRANCH, "_note": "★ 解析器修复后补跑（★ 复用原轴输出 ★）"}
out = []
replaced = False
for u in units:
    if u["arm"] == ARM and u["topic"] == TID and u["rep"] == REP:
        out.append(newu); replaced = True
    else:
        out.append(u)
if not replaced:
    out.append(newu)
units_p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("✔ units.json 已合并（★ 共 %d 个单元 ★）" % len(out))
