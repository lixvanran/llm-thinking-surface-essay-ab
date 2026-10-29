#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ build_gold.py —— ★ 金标轴的【候选 marker】→ 机械挑出【与轴库零相交】的那几个 ★

★ 为什么要有这一步（★ 纪律 ★）：
★   ★ 第一版金标用的是【题域通用词】（制度/监督/激励/工具/资源/判断/取舍…），
★     而 skill 的通用轴库用的**也是**通用治理词（规则轴=登记/公示/问责、资源轴=预算/人手、
★     兜底轴=冗余/容错、v3 的 axis_picker 里还有 验证/判断/取舍/团队/学习…）
★     ⇒ 干净组只剩 3 条（T1/T4 全灭）⇒ ★ 覆盖数会被「白捡」污染、★ 臂间不可比。★★
★   ⇒ 修法：★ 每条轴多给几个候选 marker、★ **机械挑出与轴库零相交的**做主判据；
★     ★ 挑不出 2 个的轴降级为【辅助轴】、★ 不进主判据分母。★★
★   ★ ★ 这一步发生在【任何臂跑之前】、★ 只看【轴库】不看【任何产出】⇒ 不构成对着被测对象调尺。★★★

★ 输出：gold/gold_axes.json（★ 含候选集、★ 零相交集、★ 降级标记 ★）＋ gold/leak_report.json
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAS = pathlib.Path("/run/csi/mount-root/nas/eab0d61a99b6696edb3d2aff87b585e8/.skills")

LIB = {
    "v1_path_recipes": NAS / "thinking-surface" / "references" / "path-recipes.md",
    "v1_absence": NAS / "thinking-surface" / "references" / "absence-check.md",
    "v1_fork": NAS / "thinking-surface" / "references" / "fork-map.md",
    "v1_merge": NAS / "thinking-surface" / "references" / "merge-rules.md",
    "v1_sig": NAS / "thinking-surface" / "references" / "signature-rules.md",
    "v1_v2notes": NAS / "thinking-surface" / "references" / "v2-notes.md",
    "v1_skill": NAS / "thinking-surface" / "SKILL.md",
    "v3_path_recipes": NAS / "thinking-surface-v3" / "references" / "path-recipes.md",
    "v3_slots": NAS / "thinking-surface-v3" / "references" / "mechanism-slots.md",
    "v3_fork": NAS / "thinking-surface-v3" / "references" / "fork-map.md",
    "v3_merge": NAS / "thinking-surface-v3" / "references" / "merge-rules.md",
    "v3_sig": NAS / "thinking-surface-v3" / "references" / "signature-rules.md",
    "v3_skill": NAS / "thinking-surface-v3" / "SKILL.md",
    "v3_axis_picker": NAS / "thinking-surface-v3" / "scripts" / "axis_picker.py",
}

# ★ 候选 marker：★ 目标是【轴特有、★ 又是一篇好文章自然会写出来的词】★★
CAND = {
 "T1": ("你如何看待高考英语作文？", [
   ("T1-A1", "应试导向与真实能力导向的冲突",
    ["千篇一律", "背范文", "套话", "中考", "应试"], ["模板", "套路", "应试"]),
   ("T1-A2", "评分机制与真实写作能力的脱节",
    ["阅卷老师", "评分标准", "打分标准", "压分", "考试院"], ["评分", "阅卷", "标准"]),
   ("T1-A3", "英语作为工具的实际价值",
    ["原版", "技术资料", "论文", "看原版", "语料"], ["工具", "文献", "交流"]),
   ("T1-A4", "教育公平与资源差异",
    ["寒门", "城乡", "差距", "农村", "生源"], ["公平", "城乡", "资源"]),
   ("T1-A5", "写作能力本身的迁移价值",
    ["表达力", "逻辑", "迁移", "语感", "组织"], ["写作能力", "思维", "迁移"]),
   ("T1-A6", "机器批改与 AI 带来的变数",
    ["批改", "算法", "自动评分", "AI", "误判"], ["机器", "批改", "人工智能"]),
 ]),
 "T2": ("你如何看待腐败现象？", [
   ("T2-A1", "制度设计与权力制衡",
    ["制衡", "一把手", "审批", "权力清单", "留痕"], ["制度", "制衡", "权力"]),
   ("T2-A2", "监督与问责",
    ["举报", "巡视", "纪检", "审计", "公开栏"], ["监督", "问责", "透明"]),
   ("T2-A3", "激励机制与利益结构",
    ["寻租", "利益输送", "回扣", "分红", "围标"], ["激励", "利益", "寻租"]),
   ("T2-A4", "文化传统与社会风气",
    ["风气", "潜规则", "人情", "酒桌", "上行下效"], ["文化", "风气", "传统"]),
   ("T2-A5", "经济根源与分配失衡",
    ["贫富", "垄断", "寻利", "挤占", "机会不均"], ["经济", "分配", "失衡"]),
   ("T2-A6", "个人自律与道德底线",
    ["底线", "自律", "洁癖", "滑坡", "第一口"], ["自律", "道德", "底线"]),
 ]),
 "T3": ("你如何看待“如果断了电，还是得靠人而不是 AI”这一观点？", [
   ("T3-A1", "物理依赖与 AI 的能力边界",
    ["断电", "电网", "发电", "机房", "断网"], ["断电", "依赖", "边界"]),
   ("T3-A2", "人的不可替代性（现场判断/协作）",
    ["现场", "救火", "临时判断", "换位", "手写"], ["不可替代", "现场", "判断"]),
   ("T3-A3", "过度依赖导致能力退化",
    ["退化", "懒", "空白", "丢手艺", "温水"], ["退化", "过度依赖", "依赖"]),
   ("T3-A4", "冗余与应急预案",
    ["预案", "演练", "手电", "发报机", "备用"], ["冗余", "备用", "预案"]),
   ("T3-A5", "“靠人”本身的不靠谱",
    ["靠人", "人也会", "不可靠", "甩锅", "总有人不在"], ["靠人", "人也会", "不可靠"]),
   ("T3-A6", "应急能力建设与长期准备",
    ["应急", "演练", "常态化", "平时", "储备"], ["应急", "长期", "训练"]),
 ]),
 "T4": ("你如何看待“问题的解决能力是 AI 时代最重要的能力之一”这一观点？", [
   ("T4-A1", "问题定义与诊断（先找对问题）",
    ["找对问题", "问对问题", "定义清楚", "症状", "病因"], ["定义", "诊断", "找对问题"]),
   ("T4-A2", "拆解与假设验证",
    ["假设", "证伪", "拆成", "试错", "小步"], ["拆解", "验证", "假设"]),
   ("T4-A3", "AI/工具作为能力放大器",
    ["放大", "杠杆", "省力", "帮手", "效率"], ["放大器", "杠杆", "工具"]),
   ("T4-A4", "协作与跨域",
    ["协作", "跨领域", "组队", "同行", "外部专家"], ["协作", "跨领域", "团队"]),
   ("T4-A5", "学习迁移与元能力",
    ["迁移", "举一反三", "自学", "复盘", "学会学"], ["迁移", "学习", "元能力"]),
   ("T4-A6", "不确定条件下的取舍判断",
    ["取舍", "权衡", "赌", "两难", "止损"], ["取舍", "不确定", "判断"]),
 ]),
}


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def main():
    libs = {k: read(v) for k, v in LIB.items()}
    doc = {
        "_meta": {
            "written": "2026-10-29T08:05:00Z",
            "revised": "2026-10-29T08:20:00Z（★ 候选 marker 版、★ 跑任何臂之前定死 ★）",
            "design_rule": "★ 每条轴给 4-6 个候选 marker；★ 机械取【与轴库零相交】的前 3 个做主判据；★ 零相交不足 2 个的轴降级为辅助轴（不进主判据分母）。★★",
            "hit_rule": "★ 轴命中 = 该轴【零相交 marker】至少出现 1 次（宽松）；★ 严格口径 = 全部 3 个都出现。★★",
            "saturation_rule": "★ 事前定死（双向）：★ 若直调臂 B0 的 D1 > 0.75 ⇒ 该题判饱和、不作主判据、只报数字；★ 若 B0 的 D1 < 0.15 ⇒ 该题判 marker 太生僻、不可用、退出主判据，★ 且不许因此改 marker（★ 改了就重跑全部 ★）。★★",
            "no_fitting": "★ marker 的挑选只看了【轴库文本】、★ 没看任何臂的产出 ⇒ 不构成对着被测对象调尺。★★★",
        },
        "topics": {},
    }
    report = {"_meta": {"note": "★ 候选 marker × 轴库词表、子串级相交 ★"}, "topics": {}}
    for tid, (prompt, axes) in CAND.items():
        rows = []
        for aid, name, cands, generic in axes:
            hit_map = {}
            for c in cands:
                where = [k for k, v in libs.items() if c in v]
                if where:
                    hit_map[c] = where
            clean = [c for c in cands if c not in hit_map]
            rows.append({"id": aid, "name": name, "candidates": cands,
                         "generic_first_draft": generic,
                         "collisions": hit_map,
                         "markers": clean[:3],
                         "n_clean": len(clean),
                         "primary": len(clean) >= 2})
        n_primary = sum(1 for r in rows if r["primary"])
        doc["topics"][tid] = {"prompt": prompt, "genre_hint": "评论/观点文章",
                              "axes": [{"id": r["id"], "name": r["name"], "markers": r["markers"]}
                                       for r in rows if r["primary"]],
                              "axes_aux": [{"id": r["id"], "name": r["name"], "markers": r["markers"],
                                            "candidates": r["candidates"]} for r in rows if not r["primary"]]}
        report["topics"][tid] = {"prompt": prompt, "axes": rows,
                                 "n_primary_axes": n_primary,
                                 "n_aux_axes": len(rows) - n_primary}
        print("  %s %s" % (tid, prompt))
        for r in rows:
            flag = "★ 主判据" if r["primary"] else "☆ 辅助轴"
            print("     %s %-8s %-24s 零相交 %d/%d %s"
                  % (flag, r["id"], r["name"][:22], r["n_clean"], len(r["candidates"]),
                     (("→ " + "、".join(r["markers"])) if r["primary"] else "★ 凑不出 2 个")))
        print("     ⇒ 主判据轴 %d 条" % n_primary)

    (ROOT / "gold" / "gold_axes.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "gold" / "leak_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tot_p = sum(len(t["axes"]) for t in doc["topics"].values())
    tot_a = sum(len(t["axes_aux"]) for t in doc["topics"].values())
    print("\n  ⇒ 主判据轴合计 %d 条 ｜ 辅助轴 %d 条" % (tot_p, tot_a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
