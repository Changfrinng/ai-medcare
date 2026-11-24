"""
AI-MedCare 後端 API（FastAPI）
開發者：CY團隊

提供藥品資料查詢、外觀特徵比對、用藥安全檢核與 RAG 衛教問答的 REST API，
並同時供應 frontend/ 的 PWA 靜態檔案。

正式版擴充點（以 TODO 標示）：
  - /api/recognize：串接 YOLO 偵測、ViT 分類、PaddleOCR 刻痕辨識
  - 資料層：改用 PostgreSQL + pgvector，並匯入食藥署、健保署官方資料
  - /api/chat：檢索結果交給經審核的 LLM 生成，並保留來源標示
  - 身分驗證：OAuth 2.0 + RBAC（民眾／護理師／藥師／管理者），多租戶隔離
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DB = json.loads((ROOT / "data" / "drugs.json").read_text(encoding="utf-8"))
DRUGS: dict[str, dict] = {d["id"]: d for d in DB["drugs"]}
LEVEL_ORDER = {"major": 0, "moderate": 1, "minor": 2}

app = FastAPI(
    title="AI-MedCare API",
    description="AI 智慧藥物影像辨識暨用藥衛教系統 — 開發者：CY團隊",
    version=DB["_meta"]["version"],
    contact={"name": "CY團隊"},
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- models ----------
class Features(BaseModel):
    colors: list[str] = Field(default_factory=list, examples=[["white"]])
    shape: Optional[str] = Field(None, examples=["round"])
    form: Optional[str] = Field(None, examples=["tablet"])
    imprint: Optional[str] = Field(None, examples=["AML5"])


class Profile(BaseModel):
    allergy: list[str] = Field(default_factory=list, examples=[["penicillin"]])
    pregnant: bool = False
    lactation: bool = False
    elderly: bool = False
    child: bool = False
    renal: bool = False
    hepatic: bool = False


class SafetyRequest(BaseModel):
    drug_ids: list[str] = Field(examples=[["warfarin", "aspirin", "omeprazole"]])
    profile: Profile = Profile()


class ChatRequest(BaseModel):
    question: str = Field(examples=["華法林可以吃葡萄柚嗎？"])
    drug_id: Optional[str] = None


# ---------- core logic (mirrors the frontend engine) ----------
NEAR = {"round": {"oval"}, "oval": {"round", "oblong"}, "oblong": {"oval", "capsule"}, "capsule": {"oblong"}}


def match_drugs(f: Features, top_k: int = 3) -> list[dict]:
    imp = re.sub(r"[^A-Z0-9]", "", (f.imprint or "").upper())
    results = []
    for d in DRUGS.values():
        score, why = 0.0, []
        hit = len([c for c in f.colors if c in d["color"]])
        cs = hit / max(len(f.colors), len(d["color"])) if f.colors else 0
        score += 35 * cs
        if cs:
            why.append("顏色")
        if f.shape == d["shape"]:
            score += 25
            why.append("形狀")
        elif d["shape"] in NEAR.get(f.shape or "", set()):
            score += 10
        if f.form == d["form"]:
            score += 10
        if imp:
            di = d["imprint"].upper()
            if di == imp:
                score += 30
                why.append("刻痕完全相符")
            else:
                common = sum(1 for a, b in zip(di, imp) if a == b)
                r = common / max(len(di), len(imp))
                if r >= 0.5:
                    score += 30 * r * 0.7
                    why.append("刻痕部分相符")
                elif di in imp or imp in di:
                    score += 15
                    why.append("刻痕部分相符")
        max_score = 100 if imp else 70
        results.append({"id": d["id"], "zh": d["zh"], "en": d["en"], "strength": d["strength"],
                        "license": d["license"], "score": round(score / max_score * 100), "matched": why})
    results.sort(key=lambda x: -x["score"])
    top = results[:top_k]
    return top


def interactions_for(ids: list[str]) -> list[dict]:
    out = [i for i in DB["interactions"] if i["a"] in ids and i["b"] in ids]
    return sorted(out, key=lambda i: LEVEL_ORDER[i["level"]])


def safety_check(ids: list[str], p: Profile) -> list[dict]:
    alerts = [{"level": i["level"], "type": "interaction", "title": f"{DRUGS[i['a']]['zh']} ＋ {DRUGS[i['b']]['zh']}", "text": i["note"]}
              for i in interactions_for(ids)]
    for g, label in DB["duplicateGroups"].items():
        hit = [i for i in ids if g in DRUGS[i]["groups"]]
        if len(hit) > 1 and g in ("statin",):
            alerts.append({"level": "moderate", "type": "duplicate", "title": f"重複用藥：{label}", "text": "、".join(DRUGS[i]["zh"] for i in hit)})
    for g in p.allergy:
        for i in ids:
            if g in DRUGS[i]["groups"]:
                alerts.append({"level": "major", "type": "allergy", "title": f"過敏警示：{DRUGS[i]['zh']}", "text": f"屬於{DB['allergyGroups'].get(g, g)}"})
    for i in ids:
        d = DRUGS[i]
        if p.pregnant:
            alerts.append({"level": "major" if re.search("禁用|避免|不建議", d["special"]["pregnancy"]) else "minor", "type": "population", "title": f"孕期：{d['zh']}", "text": d["special"]["pregnancy"]})
        if p.elderly:
            alerts.append({"level": "minor", "type": "population", "title": f"高齡者：{d['zh']}", "text": d["special"]["elderly"]})
        if p.renal and "無需" not in d["renal"]:
            alerts.append({"level": "moderate", "type": "organ", "title": f"腎功能：{d['zh']}", "text": d["renal"]})
        if p.hepatic and "無需" not in d["hepatic"]:
            alerts.append({"level": "moderate", "type": "organ", "title": f"肝功能：{d['zh']}", "text": d["hepatic"]})
        if d["highAlert"]:
            alerts.append({"level": "moderate", "type": "high_alert", "title": f"高警訊藥物：{d['zh']}", "text": "需雙人核對並定期監測"})
    return sorted(alerts, key=lambda a: LEVEL_ORDER[a["level"]])


INTENTS = {
    "urgent": r"胸痛|呼吸困難|昏倒|昏厥|過量|誤食|臉腫|抽搐",
    "missed": r"忘記|漏吃|漏服|兩顆|加倍",
    "side": r"副作用|不舒服|不適|頭暈",
    "timing": r"什麼時候|飯前|飯後|睡前|時間",
    "food": r"葡萄柚|食物|酒|咖啡|牛奶|保健|中藥",
    "preg": r"懷孕|孕婦|哺乳",
    "storage": r"保存|冰箱",
}


def retrieve(question: str, drug_id: Optional[str]) -> list[dict]:
    """RAG 檢索：找出問題提及的藥物，回傳相關衛教段落（含來源）。"""
    q = question.lower()
    hits = [d for d in DRUGS.values() if d["zh"].split("（")[0] in question or d["en"].split(" ")[0].lower() in q]
    if not hits and drug_id in DRUGS:
        hits = [DRUGS[drug_id]]
    passages = []
    for d in hits[:2]:
        for key, field in [("missed", "missed"), ("timing", "timing"), ("food", "food"), ("storage", "storage")]:
            if re.search(INTENTS[key], question):
                passages.append({"drug": d["id"], "section": field, "text": d[field]})
        if re.search(INTENTS["side"], question):
            passages.append({"drug": d["id"], "section": "common", "text": "、".join(d["common"])})
            passages.append({"drug": d["id"], "section": "serious", "text": "；".join(d["serious"])})
        if re.search(INTENTS["preg"], question):
            passages.append({"drug": d["id"], "section": "pregnancy", "text": d["special"]["pregnancy"]})
        if not passages:
            passages.append({"drug": d["id"], "section": "use", "text": d["use"]})
    return passages


# ---------- routes ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "developer": "CY團隊", "version": DB["_meta"]["version"], "drugs": len(DRUGS)}


@app.get("/api/drugs")
def list_drugs(q: str = ""):
    ql = q.lower()
    items = [d for d in DRUGS.values() if not ql or ql in " ".join([d["zh"], d["en"], d["brand"], d["license"], d["imprint"], d["klass"]]).lower()]
    return [{k: d[k] for k in ("id", "zh", "en", "strength", "license", "nhi", "klass", "color", "shape", "imprint", "highAlert")} for d in items]


@app.get("/api/drugs/{drug_id}")
def get_drug(drug_id: str):
    if drug_id not in DRUGS:
        raise HTTPException(404, "找不到此藥品")
    return DRUGS[drug_id]


@app.post("/api/match")
def match(features: Features):
    cands = match_drugs(features)
    lookalike = len(cands) > 1 and cands[0]["score"] - cands[1]["score"] < 12
    return {"candidates": cands, "lookalike_warning": lookalike, "reject": cands[0]["score"] < 45,
            "notice": "不得僅依影像確認藥物，必須與藥袋、處方或藥師核對。"}


@app.post("/api/recognize")
async def recognize(image: UploadFile = File(...)):
    """影像辨識端點。TODO：串接 YOLO 偵測 → ViT 分類 → PaddleOCR 刻痕 → pgvector 相似搜尋。"""
    data = await image.read()
    if not data:
        raise HTTPException(400, "影像為空")
    return {"status": "model_not_deployed", "bytes": len(data),
            "message": "伺服器端影像模型尚未部署，請使用前端特徵擷取結果呼叫 /api/match。"}


@app.post("/api/safety-check")
def safety(req: SafetyRequest):
    unknown = [i for i in req.drug_ids if i not in DRUGS]
    if unknown:
        raise HTTPException(400, f"未知藥品：{', '.join(unknown)}")
    return {"alerts": safety_check(req.drug_ids, req.profile)}


@app.post("/api/chat")
def chat(req: ChatRequest):
    if re.search(INTENTS["urgent"], req.question):
        return {"answer": "這可能是緊急狀況，請立即撥打 119 或前往急診，並攜帶藥袋。", "sources": [], "urgent": True}
    passages = retrieve(req.question, req.drug_id)
    if not passages:
        return {"answer": "請提供藥袋上的藥品名稱，我才能依審核過的資料回答。", "sources": []}
    # TODO：將 passages 作為 context 交給經審核的 LLM 生成回答（禁止超出來源內容）。
    answer = "\n".join(f"{DRUGS[p['drug']]['zh']}：{p['text']}" for p in passages)
    if re.search(r"兩顆|加倍", req.question):
        answer = "不建議自行加倍服藥。\n" + answer
    return {"answer": answer, "sources": [{"drug": p["drug"], "section": p["section"], "origin": "AI-MedCare 示範知識庫"} for p in passages]}


@app.get("/fhir/MedicationKnowledge/{drug_id}")
def fhir_medication_knowledge(drug_id: str):
    """HL7 FHIR R4 MedicationKnowledge（簡化），供 HIS／EMR 串接。"""
    d = get_drug(drug_id)
    return {
        "resourceType": "MedicationKnowledge", "id": d["id"], "status": "active",
        "code": {"coding": [{"system": "urn:tw:nhi:drug-code", "code": d["nhi"]}], "text": f"{d['en']} {d['strength']}"},
        "synonym": [d["zh"], d["brand"]],
        "doseForm": {"text": d["form"]},
        "drugCharacteristic": [
            {"type": {"text": "color"}, "valueString": "/".join(d["color"])},
            {"type": {"text": "shape"}, "valueString": d["shape"]},
            {"type": {"text": "imprint-code"}, "valueString": d["imprint"]},
        ],
        "regulatory": [{"regulatoryAuthority": {"display": "衛生福利部食品藥物管理署"}, "substitution": [], "schedule": [{"schedule": {"text": d["license"]}}]}],
    }


# Serve the PWA at "/"
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
