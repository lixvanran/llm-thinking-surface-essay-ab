#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ runner.py —— ★ skill 各版本 vs 直调 LLM 的对照跑批器 ★

★ 纪律（★ 全部事前定死 ★）：
★   ★ 只用 MiniMax（★ OpenRouter 额度已用尽 ★）
★   ★ 模型固定 MiniMax-M3、★ 温度 0.7（生成）、★ 每调用独立、★ 失败重试 ≤2 且【不换提示】★★
★   ★ 【<think> 必须剥掉】★ ——★ MiniMax 把推理内联在 content 里、★ 不剥会污染正文 ★
★   ★ 增量落盘：★ 每调一行 JSONL ＋ 正文单独存 md ⇒ ★ 中途挂了已跑的还在 ★
★   ★ 【不补造】★ ——★ 轴选择解析失败就【重试一次】、★ 再失败就【记该臂该次失败】、★ 不伪造数据 ★★
"""
import argparse, concurrent.futures as cf, hashlib, json, os, pathlib, re, sys, time
import urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAS = pathlib.Path("/run/csi/mount-root/nas/eab0d61a99b6696edb3d2aff87b585e8/.skills")
OUT = ROOT / "out"
TXT = OUT / "texts"
CALLS = OUT / "calls.jsonl"
API = "https://api.minimaxi.com/v1/chat/completions"
MODEL = "MiniMax-M3"

SKILL_PKG = {
    "A1": {
        "name": "thinking-surface",
        "skill_md": NAS / "thinking-surface" / "SKILL.md",
        "refs": [NAS / "thinking-surface" / "references" / "path-recipes.md",
                 NAS / "thinking-surface" / "references" / "absence-check.md",
                 NAS / "thinking-surface" / "references" / "fork-map.md",
                 NAS / "thinking-surface" / "references" / "signature-rules.md",
                 NAS / "thinking-surface" / "references" / "merge-rules.md"],
    },
    "A2": {
        "name": "thinking-surface-v3",
        "skill_md": NAS / "thinking-surface-v3" / "SKILL.md",
        "refs": [NAS / "thinking-surface-v3" / "references" / "path-recipes.md",
                 NAS / "thinking-surface-v3" / "references" / "mechanism-slots.md",
                 NAS / "thinking-surface-v3" / "references" / "fork-map.md",
                 NAS / "thinking-surface-v3" / "references" / "signature-rules.md",
                 NAS / "thinking-surface-v3" / "references" / "merge-rules.md"],
    },
    "A3": {  # ★ v3 的【签名不注入】修正臂（★ 按 Round-2 实测改 ★）
        "name": "thinking-surface-v3（签名不注入生成提示）",
        "skill_md": NAS / "thinking-surface-v3" / "SKILL.md",
        "refs": [NAS / "thinking-surface-v3" / "references" / "path-recipes.md",
                 NAS / "thinking-surface-v3" / "references" / "mechanism-slots.md",
                 NAS / "thinking-surface-v3" / "references" / "fork-map.md",
                 NAS / "thinking-surface-v3" / "references" / "signature-rules.md",
                 NAS / "thinking-surface-v3" / "references" / "merge-rules.md"],
    },
}

ARMS = ["B0", "B1", "A1", "A2", "A3"]
N_BRANCH = 4          # ★ 每臂固定 4 条分支（★ 臂间配平 ★）
BASE_SYS = "你是一位中文写作助手，擅长写有观点、有论证、有收束的中文文章。"


def read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def strip_think(t):
    """★ MiniMax 把 <think> 内联在 content 里 ⇒ 必须剥（★ 否则推理文字进正文 ★）"""
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    t = re.sub(r"<think>.*$", "", t, flags=re.S)
    return t.strip()


def api_call(messages, temperature, max_tokens, timeout=240):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(
        API, data=body, method="POST",
        headers={"Authorization": "Bearer %s" % os.environ["MINIMAX_SUBSCRIPTION_KEY"],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    txt = d["choices"][0]["message"].get("content") or ""
    return strip_think(txt), d.get("usage", {}) or {}


def log_call(rec):
    with CALLS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def call(arm, topic, rep, stage, messages, temperature=0.7, max_tokens=3000, tries=3):
    """★ 单次 API 调用 ＋ 落盘 ＋ 重试（★ 同一提示、★ 不换 seed、不改内容 ★）"""
    cid = "%s__%s__r%d__%s" % (arm, topic, rep, stage)
    for attempt in range(1, tries + 1):
        t0 = time.time()
        try:
            txt, usage = api_call(messages, temperature, max_tokens)
            ok = bool(txt.strip())
            rec = {"cid": cid, "arm": arm, "topic": topic, "rep": rep, "stage": stage,
                   "attempt": attempt, "ok": ok, "ts": time.time(), "wall_s": round(time.time() - t0, 2),
                   "chars": len(txt), "usage": usage,
                   "sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest() if ok else ""}
            log_call(rec)
            if ok:
                p = TXT / (cid + ".md")
                p.write_text(txt, encoding="utf-8")
                return txt, rec
            time.sleep(2 * attempt)
        except Exception as e:
            rec = {"cid": cid, "arm": arm, "topic": topic, "rep": rep, "stage": stage,
                   "attempt": attempt, "ok": False, "ts": time.time(), "wall_s": round(time.time() - t0, 2),
                   "error": str(e)[:160]}
            log_call(rec)
            time.sleep(3 * attempt)
    return "", {"cid": cid, "ok": False}


# ───────────────────────── 提示构造 ─────────────────────────

def topic_prompt(gold, tid):
    t = gold["topics"][tid]
    return t["prompt"]


def sys_skill(arm):
    return read(SKILL_PKG[arm]["skill_md"])


def sys_skill_with_refs(arm):
    parts = ["【以下是该 skill 的完整规程（SKILL.md）】", read(SKILL_PKG[arm]["skill_md"])]
    for r in SKILL_PKG[arm]["refs"]:
        parts.append("\n\n【参考文件：%s】\n%s" % (r.name, read(r)))
    return "\n".join(parts)


def prompt_b0(gold, tid):
    return [{"role": "system", "content": BASE_SYS},
            {"role": "user", "content":
             "题目：%s\n\n请写一篇 900–1200 字的中文评论文章，要有明确的观点、具体的事实或例证、层层推进的论证，以及收束。\n直接输出正文，不要写提纲或元评论。" % topic_prompt(gold, tid)}]


def prompt_b1(gold, tid):
    return [{"role": "system", "content": BASE_SYS},
            {"role": "user", "content":
             "题目：%s\n\n请从多个角度思考这个问题，然后再写一篇 900–1200 字的中文评论文章，要有明确的观点、具体的事实或例证、层层推进的论证，以及收束。\n直接输出正文，不要写提纲或元评论。" % topic_prompt(gold, tid)}]


AX_FORMAT = """【输出格式（严格照这个 JSON，不要有别的文字）】
{"axes":[{"id":"A1","name":"这条轴的名字（≤12字）","approach":"这条轴在本题的具体做法（必须含一个可执行/可观察的动作，≥20字）","cost":"走这条轴牺牲什么、谁会不满意（≥10字）","sign_pos":["正签名1","正签名2"],"sign_neg":"这条路上不该出现的东西"}]}"""


def prompt_ax(arm, gold, tid):
    if arm == "A1":
        task = ("请按本规程的【第 1–3 步】处理下面这道题：\n"
                "第 1 步 列出这道题里的【可核验对象类别】（每类给 2–3 个具体例子）；\n"
                "第 2 步 双轨取轴：轨 A 从【参考文件 path-recipes.md】的轴库挑（过程轴），轨 B 从第 1 步的对象类别里挑（实体域轴），合并去重后【总共 3–5 条】；\n"
                "第 3 步 对每条轴做落地性闸门（必须能落到第 1 步的某个对象类别上），并写下正签名（2 个具体名词/动作）、反签名、代价。\n"
                "★ 注意：这是观点/评论类题目、没有「决策点」可写 ⇒ ★ 不要硬造决策点；★ 代价就写这条立场/角度的代价。\n"
                "★ 签名只用于后续核对，★ 不要把签名当成生成约束。\n"
                "★ 只输出 3–5 条轴、★ 数量固定、★ 不要多写。\n\n" + AX_FORMAT)
    else:
        task = ("请按本规程的【第 1–4 步】处理下面这道题：\n"
                "第 1 步 先判断【有没有真分叉点】（本题是观点类、★ 若你认为路径基本唯一、★ 就明说并只给 1–3 条轴）；\n"
                "第 2 步 拿到任务专属的分叉轴（★ 优先从【上下文/题面】里找、★ 其次自测绘、★ 通用库只做查漏；"
                "★ 运行 scripts/axis_picker.py 不可用时按参考文件 path-recipes.md 的轴清单人工查漏），共 3–5 条；\n"
                "第 3 步 把每条轴写成【五槽机制句】（谁/对谁/做什么/得到/代价）；\n"
                "第 4 步 为每条路线派生 2 个正签名（★ 必须取自五槽里的具体名词 ★）＋ 1 个反签名。\n"
                "★ 注意：这是观点/评论类题目、没有「决策点」可写 ⇒ ★ 不要硬造决策点；★ 「做什么」槽就写这条角度的具体论证动作。\n"
                "★ 只输出 3–5 条轴、★ 数量固定、★ 不要多写。\n\n" + AX_FORMAT)
    return [{"role": "system", "content": sys_skill_with_refs(arm)},
            {"role": "user", "content": task + "\n\n题目：%s" % topic_prompt(gold, tid)}]


def parse_axes(txt):
    """★ 宽容解析（★ 模型侧 schema 违规是常态 ★）＋ 不足就【不算数】、★ 不补造 ★"""
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        # ★ 退而求其次：抓第一个 {...} 平衡括号块 ★
        i = txt.find("{")
        depth = 0
        for j in range(i, len(txt)):
            if txt[j] == "{":
                depth += 1
            elif txt[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        d = json.loads(txt[i:j + 1])
                    except Exception:
                        return None
                    break
        else:
            return None
    axes = d.get("axes")
    if not isinstance(axes, list) or not axes:
        return None
    out = []
    for a in axes:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "").strip()
        if not name:
            continue
        out.append({"id": str(a.get("id") or (len(out) + 1)),
                    "name": name,
                    "approach": str(a.get("approach") or "").strip(),
                    "cost": str(a.get("cost") or "").strip(),
                    "sign_pos": [str(x) for x in (a.get("sign_pos") or []) if str(x).strip()][:3],
                    "sign_neg": str(a.get("sign_neg") or "").strip()})
    return out or None


def prompt_branch(arm, gold, tid, ax, k):
    brief = ("你负责第 %d 条轴（共 %d 条）。★ **只走这一条**，★ 不要提及其他轴、★ 不要写「我再换个角度」。\n"
             "轴名：%s\n本题的具体做法：%s\n这条路线的代价：%s\n"
             % (k, N_BRANCH, ax["name"], ax["approach"] or "（规程未给出、★ 请自己把这条轴落到本题的具体做法）",
                ax["cost"] or "（规程未给出、★ 请自己写出这条角度的代价）"))
    if arm == "A2":
        brief += "★ 正签名要点（**必须真的体现在正文里**、★ 只提一句不算兑现）：%s\n" % ("、".join(ax["sign_pos"]) or "（无）")
        brief += "★ 反签名（这条路上**不该出现**的东西）：%s\n" % (ax["sign_neg"] or "（无）")
    elif arm == "A1":
        brief += "★ 签名不在这里给（★ 本规程规定签名只用于事后核对 ★）。\n"
    elif arm == "A3":
        brief += "★ 本臂【签名不注入生成提示】（★ 按实测：签名注入会压窄分支 ★）。\n"
    brief += ("\n★ 请就这条轴写一篇 900–1200 字的中文评论文章正文（★ 只写这一条角度的论证、★ 要有具体例证、★ 不要写提纲）。")
    return [{"role": "system", "content": sys_skill(arm)},
            {"role": "user", "content": brief + "\n\n题目：%s" % topic_prompt(gold, tid)}]


def prompt_merge(arm, gold, tid, branches, axes):
    if arm == "A1":
        fmt = ("【合流】保留分歧、不要取交集、不要投票、不要「综合最优」。输出：每条路径的方案 ＋ 它覆盖的决策点 ＋ 它的代价 ＋ 它们之间真正的冲突点。\n"
               "★ 最后必须做【缺席自检】：哪些可核验对象类别一条都没碰、★ 要显式说出来。")
    else:
        fmt = ("【合流·逐条】每条路线的做法 ＋ 它覆盖的决策点 ＋ 它的代价\n"
               "【合流·冲突点】哪两条路在哪个点直接对立\n【合流·待拍板】需要读者取舍的地方（★ 给取舍条件、★ 不要无条件排序 ★）\n"
               "★ 不许投票、不许取交集、不许「综合最优」。")
    body = "\n\n".join("【路径 %d：%s】\n%s" % (i + 1, axes[i]["name"] if i < len(axes) else "?", b)
                       for i, b in enumerate(branches))
    return [{"role": "system", "content": sys_skill(arm)},
            {"role": "user", "content":
             "下面是同一个题目下、%d 条独立路径各自的产出（★ 各路径互相看不见对方 ★）。\n%s\n\n%s\n\n"
             "★ 最终产出就是【给读者的最终回答】、★ 请直接输出它（★ 不要写「以下是合流」之类元评论 ★）。"
             % (len(branches), body, fmt)}]


# ───────────────────────── 单臂单次（topic, rep） ─────────────────────────

def run_arm_unit(arm, gold, tid, rep):
    t0 = time.time()
    if arm in ("B0", "B1"):
        msgs = prompt_b0(gold, tid) if arm == "B0" else prompt_b1(gold, tid)
        txt, rec = call(arm, tid, rep, "final", msgs, max_tokens=3000)
        return {"arm": arm, "topic": tid, "rep": rep, "ok": bool(txt), "final_chars": len(txt),
                "stages": ["final"], "wall_s": round(time.time() - t0, 1), "n_calls": 1}

    # ★ 选轴 ★
    ax_txt, ax_rec = call(arm, tid, rep, "axes", prompt_ax(arm, gold, tid), max_tokens=2000)
    axes = parse_axes(ax_txt) if ax_txt else None
    if not axes:
        # ★ 再试一次（★ 同一提示、★ 不改内容 ★）★★
        ax_txt2, _ = call(arm, tid, rep, "axes_retry", prompt_ax(arm, gold, tid), max_tokens=2000)
        axes = parse_axes(ax_txt2) if ax_txt2 else None
    if not axes:
        return {"arm": arm, "topic": tid, "rep": rep, "ok": False, "fail": "axes_parse_failed",
                "stages": ["axes"], "wall_s": round(time.time() - t0, 1), "n_calls": 2}

    # ★ 分支（★ 固定 4 条、★ 超过 4 条只取前 4 条、★ 不足则用末条补齐并标记 ★）★★
    axes = axes[:N_BRANCH]
    while len(axes) < N_BRANCH:
        axes.append(dict(axes[-1], id="dup"))
    branches = []
    with cf.ThreadPoolExecutor(max_workers=N_BRANCH) as ex:
        futs = [ex.submit(call, arm, tid, rep, "branch%d" % (k + 1),
                          prompt_branch(arm, gold, tid, axes[k], k + 1), max_tokens=3000)
                for k in range(N_BRANCH)]
        for f in futs:
            b, _ = f.result()
            branches.append(b)
    if not all(branches):
        return {"arm": arm, "topic": tid, "rep": rep, "ok": False, "fail": "branch_failed",
                "stages": ["axes", "branch"], "wall_s": round(time.time() - t0, 1), "n_calls": 3 + N_BRANCH}

    # ★ 合流 ★
    mg, _ = call(arm, tid, rep, "merge", prompt_merge(arm, gold, tid, branches, axes), max_tokens=4000)
    if not mg:
        return {"arm": arm, "topic": tid, "rep": rep, "ok": False, "fail": "merge_failed",
                "stages": ["axes", "branch", "merge"], "wall_s": round(time.time() - t0, 1), "n_calls": 5 + N_BRANCH}
    return {"arm": arm, "topic": tid, "rep": rep, "ok": True, "final_chars": len(mg),
            "n_axes": len(axes), "axes_names": [a["name"] for a in axes],
            "stages": ["axes", "branch", "merge"], "wall_s": round(time.time() - t0, 1),
            "n_calls": 5 + N_BRANCH}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--topics", default="T1,T2,T3,T4")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()

    gold = json.loads((ROOT / "gold" / "gold_axes.json").read_text(encoding="utf-8"))
    TXT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    units = [(arm, tid, rep) for arm in a.arms.split(",") for tid in a.topics.split(",")
             for rep in range(1, a.reps + 1)]
    print("★ 跑批：%d 臂 × %d 题 × %d rep = %d 个单元（★ 每单元 ≤6 次调用 ★）"
          % (len(a.arms.split(",")), len(a.topics.split(",")), a.reps, len(units)))
    res = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_arm_unit, arm, gold, tid, rep): (arm, tid, rep) for (arm, tid, rep) in units}
        done = 0
        for f in cf.as_completed(futs):
            r = f.result()
            res.append(r)
            done += 1
            print("  [%2d/%2d] %-4s %s rep%d → %s（%d 字、%d 次调用、%.0fs）"
                  % (done, len(units), r["arm"], r["topic"], r["rep"],
                     "OK" if r["ok"] else "✘ " + r.get("fail", "?"),
                     r.get("final_chars", 0), r.get("n_calls", 0), r.get("wall_s", 0)))
    (OUT / "units.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in res if r["ok"])
    print("\n  ★ 完成 %d/%d ｜ 失败 %d" % (ok, len(res), len(res) - ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
