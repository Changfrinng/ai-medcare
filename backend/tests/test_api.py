from fastapi.testclient import TestClient
from backend.main import app

c = TestClient(app)

def test_health():
    r = c.get("/api/health").json()
    assert r["developer"] == "CY團隊" and r["drugs"] == 15

def test_match_imprint_wins():
    r = c.post("/api/match", json={"colors": ["white"], "shape": "round", "form": "tablet", "imprint": "AML5"}).json()
    assert r["candidates"][0]["id"] == "amlodipine"

def test_lookalike_without_imprint():
    r = c.post("/api/match", json={"colors": ["white"], "shape": "round", "form": "tablet"}).json()
    assert r["lookalike_warning"] is True

def test_safety_major_interaction_and_allergy():
    r = c.post("/api/safety-check", json={"drug_ids": ["warfarin", "aspirin", "amoxicillin"], "profile": {"allergy": ["penicillin"]}}).json()
    titles = [a["title"] for a in r["alerts"]]
    assert r["alerts"][0]["level"] == "major"
    assert any("過敏" in t for t in titles) and any("華法林 ＋ 阿斯匹靈" in t for t in titles)

def test_chat_urgent_and_rag():
    assert c.post("/api/chat", json={"question": "我胸痛"}).json()["urgent"]
    r = c.post("/api/chat", json={"question": "華法林可以吃葡萄柚嗎"}).json()
    assert r["sources"] and r["sources"][0]["drug"] == "warfarin"

def test_fhir_and_frontend():
    assert c.get("/fhir/MedicationKnowledge/warfarin").json()["resourceType"] == "MedicationKnowledge"
    assert "CY團隊" in c.get("/").text

def test_visits():
    a = c.get("/api/visits").json()["count"]
    b = c.post("/api/visits").json()["count"]
    assert b == a + 1

def test_food_interactions():
    r = c.get("/api/food-interactions", params={"drug_ids": "simvastatin,warfarin", "foods": "grapefruit"}).json()
    assert r["interactions"][0]["drug"] == "simvastatin" and r["interactions"][0]["level"] == "major"
