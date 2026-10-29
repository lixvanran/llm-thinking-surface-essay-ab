#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ leak_check.py —— ★ 金标 marker × skill 轴库词表的【子串级】相交检查 ★

★ 为什么必须做（★ 纪律 ★）：
★   ★ 本实验的宽度判据是【外部金标覆盖】。★ 如果金标里的词恰好在 skill 的【通用轴库】里，
★     那「用轴库的臂」等于白捡了这些 marker ⇒ ★ 覆盖数被污染、★ 臂间不可比。★★
★   ⇒ 输出【相交组】与【不相交组】：★ 【不相交组】才是干净的宽度度量。★★★★

★ 输出：gold/leak_report.json（★ 事前生成、★ 事后不得改 ★）
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAS = pathlib.Path("/run/csi/mount-root/nas/eab0d61a99b6696edb3d2aff87b585e8/.skills")
GOLD = ROOT / "gold" / "gold_axes.json"

LIB_FILES = {
    "v1_path_recipes": NAS / "thinking-surface" / "references" / "path-recipes.md",
    "v1_other_refs": [
        NAS / "thinking-surface" / "references" / "absence-check.md",
        NAS / "thinking-surface" / "references" / "fork-map.md",
        NAS / "thinking-surface" / "references" / "merge-rules.md",
        NAS / "thinking-surface" / "references" / "signature-rules.md",
        NAS / "thinking-surface" / "references" / "v2-notes.md",
    ],
    "v3_path_recipes": NAS / "thinking-surface-v3" / "references" / "path-recipes.md",
    "v3_axis_picker": NAS / "thinking-surface-v3" / "scripts" / "axis_picker.py",
    "v3_other_refs": [
        NAS / "thinking-surface-v3" / "references" / "mechanism-slots.md",
        NAS / "thinking-surface-v3" / "references" / "fork-map.md",
        NAS / "thinking-surface-v3" / "references" / "merge-rules.md",
        NAS / "thinking-surface-v3" / "references" / "signature-rules.md",
    ],
    "v1_skill_md": NAS / "thinking-surface" / "SKILL.md",
    "v3_skill_md": NAS / "thinking-surface-v3" / "SKILL.md",
}


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def main():
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    libs = {}
    for k, v in LIB_FILES.items():
        libs[k] = read(v) if isinstance(v, pathlib.Path) else "\n".join(read(x) for x in v)

    report = {"_meta": {"checked_at": "2026-10-29T08:10:00Z",
                         "rule": "★ 子串级相交（★ marker 只要在轴库文本里【出现过】就算相交 ★）★★"},
              "libs": {k: len(v) for k, v in libs.items()},
              "topics": {}}

    # ★ 轴库【自己】在 SKILL.md/轴库里声明的轴名与示例词（★ 单独拎出来、★ 因为那是「臂真正会拿到的东西」★★）
    for tid, t in gold["topics"].items():
        rows = []
        for ax in t["axes"]:
            hits = {}
            for mk in ax["markers"]:
                where = [k for k, v in libs.items() if mk in v]
                if where:
                    hits[mk] = where
            rows.append({"axis_id": ax["id"], "name": ax["name"], "markers": ax["markers"],
                         "hits": hits, "collided": bool(hits)})
        n_col = sum(1 for r in rows if r["collided"])
        report["topics"][tid] = {
            "prompt": t["prompt"],
            "axes": rows,
            "n_axes": len(rows),
            "n_collided_axes": n_col,
            "n_clean_axes": len(rows) - n_col,
            "clean_axis_ids": [r["axis_id"] for r in rows if not r["collided"]],
            "collided_axis_ids": [r["axis_id"] for r in rows if r["collided"]],
        }

    out = ROOT / "gold" / "leak_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("★ 泄露检查（★ 金标 marker × 轴库词表、子串级 ★）")
    for tid, r in report["topics"].items():
        print("\n  %s %s" % (tid, r["prompt"]))
        print("    轴 %d 条 ｜ 与轴库相交 %d 条 ｜ ★ 干净 %d 条" % (r["n_axes"], r["n_collided_axes"], r["n_clean_axes"]))
        for row in r["axes"]:
            if row["collided"]:
                mk_hits = "；".join("%s→%s" % (m, ",".join(h[:2] for h in w)) for m, w in row["hits"].items())
                print("      ★ 相交 %-8s %-22s %s" % (row["axis_id"], row["name"][:20], mk_hits[:110]))
        print("    ★ 干净组（★ 主判据用这组 ★）: %s" % (", ".join(r["clean_axis_ids"]) or "★ 无"))
    print("\n  → %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
