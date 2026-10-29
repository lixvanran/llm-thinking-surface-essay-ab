#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ analyze.py —— ★ 出表：★ 覆盖/缺席/分叉/成文/成本 ＋ 配对比较 ＋ 饱和闸门 ★

★ 纪律：
★   ★ 主判据 = 【金标覆盖 D1】（★ 机械、★ 零 LLM 判官 ★）
★   ★ 饱和闸门（★ 事前定死、★ 双向 ★）：★ B0 的 D1 > 0.75 ⇒ 该题饱和、退出主判据；★ < 0.15 ⇒ marker 生僻、退出。★★
★   ★ 臂间比较用【配对】（★ 同题同 rep 对齐 ★）★ ⇒ 报差值中位数 ＋ bootstrap CI ＋ 同向计数 ★
★   ★ 覆盖天然随字数涨 ⇒ ★ 必须同时报字数 ＋ 覆盖/千字 ★
"""
import json, math, pathlib, re, statistics as st
from itertools import combinations

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
TXT = OUT / "texts"

ARMS = ["B0", "B1", "A1", "A2", "A3"]
ARM_NAME = {
    "B0": "直调 LLM（无规程）",
    "B1": "一句话多角度",
    "A1": "thinking-surface v1.1",
    "A2": "thinking-surface-v3",
    "A3": "v3（签名不注入）",
}
ARMS_LABEL = {"B0": "B0", "B1": "B1", "A1": "A1", "A2": "A2", "A3": "A3"}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def bigrams(s):
    s = norm(s)
    return set(s[i:i + 2] for i in range(len(s) - 1))


def jacc(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def coverage(text, axes, strict=False):
    t = norm(text)
    hits, detail = [], {}
    for ax in axes:
        ms = ax["markers"]
        n = sum(1 for m in ms if m in t)
        ok = (n == len(ms)) if strict else (n >= 1)
        detail[ax["id"]] = {"hits": n, "of": len(ms), "ok": ok}
        if ok:
            hits.append(ax["id"])
    return (len(hits) / len(axes) if axes else 0.0), hits, detail


def text_stats(t):
    t = t or ""
    paras = [p for p in re.split(r"\n\s*\n", t) if p.strip()]
    heads = len(re.findall(r"(?m)^\s*(?:#{1,4}\s|【[^】]{2,20}】)", t))
    bullets = len(re.findall(r"(?m)^\s*[-*]\s", t))
    nums = len(re.findall(r"(?m)^\s*\d+[.、]\s", t))
    struct = len(re.findall(r"冲突点|待拍板|缺席|路径\s*\d|【路径", t))
    return {"chars": len(norm(t)), "paras": len(paras), "heads": heads,
            "bullets": bullets, "numbered": nums, "struct_markers": struct}


def bootstrap_ci(xs, iters=10000, seed=20261029):
    if not xs:
        return (float("nan"), float("nan"))
    import random
    rnd = random.Random(seed)
    n = len(xs)
    meds = []
    for _ in range(iters):
        meds.append(st.median([xs[rnd.randrange(n)] for _ in range(n)]))
    meds.sort()
    return (meds[int(0.025 * iters)], meds[int(0.975 * iters)])


def main():
    gold = json.loads((ROOT / "gold" / "gold_axes.json").read_text(encoding="utf-8"))
    leak = json.loads((ROOT / "gold" / "leak_report.json").read_text(encoding="utf-8"))
    calls = []
    if (OUT / "calls.jsonl").exists():
        for l in (OUT / "calls.jsonl").read_text(encoding="utf-8").splitlines():
            if l.strip():
                calls.append(json.loads(l))
    units = json.loads((OUT / "units.json").read_text(encoding="utf-8")) if (OUT / "units.json").exists() else []

    ok_calls = [c for c in calls if c.get("ok")]
    per_call_tok = {}
    for c in ok_calls:
        u = c.get("usage") or {}
        per_call_tok.setdefault(c["cid"], {})[c["stage"]] = u

    # ── 逐单元算指标 ──
    rows = []
    for uid in units:
        arm, tid, rep = uid["arm"], uid["topic"], uid["rep"]
        if not uid.get("ok"):
            rows.append({"arm": arm, "topic": tid, "rep": rep, "ok": False, "fail": uid.get("fail")})
            continue
        final_p = TXT / ("%s__%s__r%d__final.md" % (arm, tid, rep))
        if not final_p.exists():
            final_p = TXT / ("%s__%s__r%d__merge.md" % (arm, tid, rep))
        final = final_p.read_text(encoding="utf-8") if final_p.exists() else ""
        axes = gold["topics"][tid]["axes"]
        cov, hits, detail = coverage(final, axes)
        covs, _, _ = coverage(final, axes, strict=True)
        stt = text_stats(final)
        # 分支
        brs = []
        for k in range(1, 5):
            bp = TXT / ("%s__%s__r%d__branch%d.md" % (arm, tid, rep, k))
            if bp.exists():
                brs.append(bp.read_text(encoding="utf-8"))
        sims = [jacc(bigrams(a), bigrams(b)) for a, b in combinations(brs, 2)]
        # 成本
        cid_pre = "%s__%s__r%d__" % (arm, tid, rep)
        cc = [c for c in calls if c["cid"].startswith(cid_pre)]
        tok = sum((c.get("usage") or {}).get("total_tokens", 0) for c in cc)
        rows.append({"arm": arm, "topic": tid, "rep": rep, "ok": True, "_text": final,
                     "cov": cov, "cov_strict": covs, "n_hit": len(hits), "hits": hits,
                     "detail": detail, **stt,
                     "n_branch": len(brs),
                     "branch_sim_mean": round(sum(sims) / len(sims), 4) if sims else None,
                     "branch_sim_max": round(max(sims), 4) if sims else None,
                     "n_calls": len(cc), "tokens": tok,
                     "wall_s": round(sum(c.get("wall_s", 0) for c in cc), 1)})

    # ── 饱和闸门（★ 事前定死 ★）──
    sat = {}
    for tid in gold["topics"]:
        b0 = [r["cov"] for r in rows if r["arm"] == "B0" and r["topic"] == tid and r.get("ok")]
        m = round(sum(b0) / len(b0), 4) if b0 else None
        verdict = "★ 正常"
        if m is not None and m > 0.75:
            verdict = "★ 饱和、★ 退出主判据"
        elif m is not None and m < 0.15:
            verdict = "★ marker 生僻、★ 退出主判据"
        sat[tid] = {"B0_cov": m, "verdict": verdict, "primary": verdict == "★ 正常"}

    # ── 聚合（★ 只在通过闸门的题上做主表 ★）──
    primary_topics = [t for t in gold["topics"] if sat[t]["primary"]]
    agg = {}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm and r.get("ok") and r["topic"] in primary_topics]
        if not rs:
            continue
        agg[arm] = {
            "n": len(rs),
            "cov_mean": round(sum(r["cov"] for r in rs) / len(rs), 4),
            "cov_strict_mean": round(sum(r["cov_strict"] for r in rs) / len(rs), 4),
            "absence_mean": round(1 - sum(r["cov"] for r in rs) / len(rs), 4),
            "chars_mean": int(sum(r["chars"] for r in rs) / len(rs)),
            "cov_per_1k": round(sum(r["cov"] for r in rs) / len(rs) / (sum(r["chars"] for r in rs) / len(rs) / 1000), 4),
            "paras_mean": round(sum(r["paras"] for r in rs) / len(rs), 1),
            "heads_mean": round(sum(r["heads"] for r in rs) / len(rs), 1),
            "struct_mean": round(sum(r["struct_markers"] for r in rs) / len(rs), 1),
            "sim_mean": round(st.mean([r["branch_sim_mean"] for r in rs if r.get("branch_sim_mean") is not None]), 4)
            if any(r.get("branch_sim_mean") is not None for r in rs) else None,
            "calls_mean": round(sum(r["n_calls"] for r in rs) / len(rs), 1),
            "tokens_mean": int(sum(r["tokens"] for r in rs) / len(rs)),
            "wall_mean": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
        }

    # ── 长度对齐（★ 覆盖天然随字数涨 ⇒ ★ 必须做这一步 ★）──
    arm_means = {}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm and r.get("ok") and r["topic"] in primary_topics]
        if rs:
            arm_means[arm] = sum(r["chars"] for r in rs) / len(rs)
    Lmin = int(min(arm_means.values())) if arm_means else 0
    lmatch = {}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm and r.get("ok") and r["topic"] in primary_topics]
        if not rs:
            continue
        cs = []
        for r in rs:
            txt = r.get("_text", "")
            ax = gold["topics"][r["topic"]]["axes"]
            cs.append(coverage(txt[:Lmin], ax)[0])
        lmatch[arm] = {"cov_trunc": round(sum(cs) / len(cs), 4), "n": len(cs)}

    # ── 配对比较（★ 同题同 rep、★ 对 B0；★ A2 vs A3 单独比 ★）──
    def paired(a1, a2, key="cov"):
        idx = {}
        for r in rows:
            if r.get("ok"):
                idx[(r["arm"], r["topic"], r["rep"])] = r
        diffs, pairs = [], []
        for (arm, tid, rep), r in sorted(idx.items()):
            if arm != a1:
                continue
            if tid not in primary_topics:
                continue
            base = idx.get((a2, tid, rep))
            if not base:
                continue
            d = r[key] - base[key]
            diffs.append(d)
            pairs.append({"topic": tid, "rep": rep, "a": round(r[key], 4), "b": round(base[key], 4),
                          "d": round(d, 4)})
        if not diffs:
            return None
        lo, hi = bootstrap_ci(diffs)
        return {"n_pairs": len(diffs), "median_d": round(st.median(diffs), 4),
                "mean_d": round(sum(diffs) / len(diffs), 4), "ci95": [lo, hi],
                "n_pos": sum(1 for d in diffs if d > 0), "n_zero": sum(1 for d in diffs if d == 0),
                "n_neg": sum(1 for d in diffs if d < 0), "pairs": pairs}

    comps = {}
    for arm in ["B1", "A1", "A2", "A3"]:
        comps["%s vs B0" % arm] = paired(arm, "B0")
    comps["A3 vs A2"] = paired("A3", "A2")
    comps["A2 vs A1"] = paired("A2", "A1")

    # ★ 长度对齐后的配对 ★（★ 核心 ★）
    def paired_trunc(a1, a2):
        idx = {}
        for r in rows:
            if r.get("ok"):
                idx[(r["arm"], r["topic"], r["rep"])] = r
        diffs = []
        for (arm, tid, rep), r in sorted(idx.items()):
            if arm != a1 or tid not in primary_topics:
                continue
            b = idx.get((a2, tid, rep))
            if not b:
                continue
            ax = gold["topics"][tid]["axes"]
            diffs.append(coverage(r["_text"][:Lmin], ax)[0] - coverage(b["_text"][:Lmin], ax)[0])
        if not diffs:
            return None
        lo, hi = bootstrap_ci(diffs)
        return {"n_pairs": len(diffs), "median_d": round(st.median(diffs), 4),
                "mean_d": round(sum(diffs) / len(diffs), 4), "ci95": [lo, hi],
                "n_pos": sum(1 for d in diffs if d > 0), "n_zero": sum(1 for d in diffs if d == 0),
                "n_neg": sum(1 for d in diffs if d < 0)}

    comps_trunc = {}
    for arm in ["B1", "A1", "A2", "A3"]:
        comps_trunc["%s vs B0" % arm] = paired_trunc(arm, "B0")
    comps_trunc["A3 vs A2"] = paired_trunc("A3", "A2")
    comps_trunc["A2 vs A1"] = paired_trunc("A2", "A1")

    res = {"_meta": {"generated": "2026-10-29", "prereg_sha": "见 PREREG.md",
                     "n_calls_total": len(calls), "n_calls_ok": len(ok_calls),
                     "fail_rate": round(1 - len(ok_calls) / len(calls), 4) if calls else None},
           "saturation": sat, "primary_topics": primary_topics, "length_align_char": Lmin,
           "arm_mean_chars": {k: round(v) for k, v in arm_means.items()},
           "length_matched": lmatch, "comps_trunc": comps_trunc,
           "agg": agg, "comps": comps, "rows": rows,
           "calls": [{k: c.get(k) for k in ("cid", "stage", "attempt", "ok", "chars", "wall_s", "error")}
                     | {"usage": c.get("usage")} for c in calls]}
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 人看的表 ──
    L = []
    L.append("# 结果表 · skill 各版本 vs 直调 LLM（议论文四题）\n")
    L.append("> 判据 = 【金标覆盖 D1】（★ 机械、★ 零 LLM 判官 ★）｜ 主判据题 = %s\n"
             % ("、".join(primary_topics) if primary_topics else "★ 无"))
    L.append("## 0 · 通道健康度\n")
    L.append("| 项 | 值 |\n|---|---|")
    L.append("| API 调用 | %d（成功 %d、失败 %d、失败率 %s） |"
             % (len(calls), len(ok_calls), len(calls) - len(ok_calls),
                "%.1f%%" % (100 * res["_meta"]["fail_rate"]) if calls else "-"))
    L.append("| 完成的臂×题×rep 单元 | %d / %d |" % (sum(1 for r in rows if r.get("ok")), len(units)))
    L.append("")
    L.append("## 1 · 饱和闸门（★ 事前定死 ★）\n")
    L.append("| 题 | B0 覆盖 | 判定 |\n|---|--:|---|")
    for tid, s in sat.items():
        L.append("| %s %s | %s | %s |" % (tid, gold["topics"][tid]["prompt"][:16],
                                          s["B0_cov"], s["verdict"]))
    L.append("")
    L.append("## 2 · 主表（★ 只统计通过闸门的题 ★）\n")
    L.append("| 臂 | n | 覆盖 D1 | 严格口径 | 缺席率 | 平均字数 | 覆盖/千字 | 段落 | 小标题 | 结构标记 | 分支相似度(均) | 调用 | token | 秒 |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for arm in ARMS:
        a = agg.get(arm)
        if not a:
            continue
        L.append("| **%s** %s | %d | **%.3f** | %.3f | %.3f | %d | %.3f | %.1f | %.1f | %.1f | %s | %.1f | %d | %.0f |"
                 % (arm, ARM_NAME[arm], a["n"], a["cov_mean"], a["cov_strict_mean"], a["absence_mean"],
                    a["chars_mean"], a["cov_per_1k"], a["paras_mean"], a["heads_mean"], a["struct_mean"],
                    ("%.3f" % a["sim_mean"]) if a["sim_mean"] is not None else "-",
                    a["calls_mean"], a["tokens_mean"], a["wall_mean"]))
    L.append("")
    L.append("## 2b · ★ 长度对齐后的覆盖（★ 本次最关键的一张表 ★）\n")
    L.append("> ★ 覆盖天然随字数涨 ⇒ ★ 截到【各臂最短的平均字数 = %d 字】★ 后重算。★\n" % Lmin)
    L.append("| 臂 | 平均字数 | 原覆盖 D1 | **截到 %d 字后** | 覆盖/千字 |\n|---|--:|--:|--:|--:|" % Lmin)
    for arm in ARMS:
        a = agg.get(arm); lm = lmatch.get(arm)
        if not a or not lm:
            continue
        L.append("| **%s** %s | %d | %.3f | **%.3f** | %.3f |"
                 % (arm, ARM_NAME[arm], a["chars_mean"], a["cov_mean"], lm["cov_trunc"], a["cov_per_1k"]))
    L.append("")
    L.append("## 3 · 配对比较（★ 同题同 rep、★ 对照臂逐个比 ★）\n")
    L.append("| 对比 | n 对 | 差值中位数 | 差值均值 | bootstrap 95% CI | 同向 | 反向 | 持平 |\n|---|--:|--:|--:|---|--:|--:|--:|")
    for k, c in comps.items():
        if not c:
            continue
        L.append("| %s | %d | **%+.4f** | %+.4f | [%+.4f, %+.4f] | %d | %d | %d |"
                 % (k, c["n_pairs"], c["median_d"], c["mean_d"], c["ci95"][0], c["ci95"][1],
                    c["n_pos"], c["n_neg"], c["n_zero"]))
    L.append("")
    L.append("## 3b · ★ 配对比较（★ 长度对齐后 ★）\n")
    L.append("| 对比 | n 对 | 差值中位数 | 差值均值 | bootstrap 95% CI | 同向 | 反向 | 持平 |\n|---|--:|--:|--:|---|--:|--:|--:|")
    for k, c in comps_trunc.items():
        if not c:
            continue
        L.append("| %s | %d | **%+.4f** | %+.4f | [%+.4f, %+.4f] | %d | %d | %d |"
                 % (k, c["n_pairs"], c["median_d"], c["mean_d"], c["ci95"][0], c["ci95"][1],
                    c["n_pos"], c["n_neg"], c["n_zero"]))
    L.append("")
    L.append("## 4 · 逐题（★ 覆盖均值 · n=3 rep ★）\n")
    L.append("| 题 | " + " | ".join(ARMS) + " |\n|---|" + "---|" * len(ARMS))
    for tid in gold["topics"]:
        cells = []
        for arm in ARMS:
            rs = [r["cov"] for r in rows if r["arm"] == arm and r["topic"] == tid and r.get("ok")]
            cells.append("%.3f" % (sum(rs) / len(rs)) if rs else "-")
        L.append("| %s %s | %s |" % (tid, gold["topics"][tid]["prompt"][:14], " | ".join(cells)))
    L.append("")
    L.append("## 5 · 每题每臂的命中轴（★ 哪条轴被覆盖、★ 哪条缺席 ★）\n")
    for tid in gold["topics"]:
        L.append("**%s %s**\n" % (tid, gold["topics"][tid]["prompt"]))
        for arm in ARMS:
            rs = [r for r in rows if r["arm"] == arm and r["topic"] == tid and r.get("ok")]
            if not rs:
                continue
            cnt = {}
            for r in rs:
                for h in r["hits"]:
                    cnt[h] = cnt.get(h, 0) + 1
            L.append("- `%s`：%s" % (arm, "、".join("%s %d/%d" % (k, v, len(rs)) for k, v in sorted(cnt.items()))
                                        or "★ 一条都没命中"))
        L.append("")
    (OUT / "results.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
