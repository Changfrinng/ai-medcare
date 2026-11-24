# AI-MedCare 智慧藥物影像辨識暨用藥衛教系統

AI-powered Medication Image Recognition and Patient Education System

**開發者：CY團隊**　·　版本 0.1.0-demo（臨床前原型）

適合全臺灣醫療院所、診所、藥局、護理之家、長照機構、居家護理及一般民眾使用的智慧用藥安全平台。採用漸進式網頁應用程式（PWA），同一套程式可在 iPhone、Android、iPad、Android 平板、Windows、macOS 與行動護理工作站上使用，並可「加入主畫面」安裝。

> ⚠️ 本系統為研究與教學原型。辨識結果不能取代醫師、藥師與護理給藥核對。

### 資料來源

- **許可證資料**（許可證字號、品名、劑型、類別、申請商、製造廠、效期）：衛生福利部食品藥物管理署「全部藥品許可證」資料集。
- **藥品外觀**（顏色、形狀、刻痕、尺寸、正反面標註、官方外觀照片）：食藥署「藥品外觀資料集」（data.gov.tw 資料集 9120，每 7 日更新）。照片直接連結食藥署圖檔伺服器 `mcp.fda.gov.tw`。
- 兩者皆於 2026-11-24 下載，依「政府資料開放授權條款－第1版」使用。每種成分選一個有效許可證作為代表產品，同成分其他廠牌的外觀可能不同。
- 健保代碼待串接健保署資料；臨床衛教內容為一般藥學知識摘要，正式上線前須由藥師審核；護理核對頁的藥品條碼仍為示範值。

---

## 功能對照（依規格書）

| 規格章節 | 功能 | 本原型實作 |
|---|---|---|
| 一、三 | AI 藥物影像辨識 | 拍照／上傳 → 背景估計去背 → 主體偵測 → 顏色（k-means）、形狀（長寬比）、雙色膠囊、清晰度檢查 → 刻痕輸入 → Top-3 候選與相似度 → **藥袋／藥師確認關卡**（未確認即停止） |
| 一、三 | 藥袋文字、條碼 | 藥袋文字比對藥名／許可證／健保碼；條碼比對 |
| 四、五 | 臺灣藥品資料庫 | 15 種常用藥，欄位涵蓋基本資料、許可證、健保碼、成分、外觀、藥理、臨床、安全、特殊族群、肝腎功能、品質管理 |
| 六 | GenAI 衛教（RAG） | 先檢索藥品衛教段落再組成回答、標示來源；緊急關鍵字導向 119；語音輸入與朗讀 |
| 六 | 12 項衛教 | 用途、機轉、使用方式、服藥時間、常見／嚴重副作用、忘記服藥、食物與藥物交互作用、保存、特殊族群、Teach-back 測驗 |
| 一、七 | 用藥安全警示 | 交互作用（18 組）、重複用藥、過敏、孕婦／哺乳／兒童／高齡、肝腎功能、高警訊藥物 |
| 七 | 民眾版／醫護專業版 | 右上角切換；專業版另有藥理機轉、臨床劑量參考、Cockcroft-Gault 肝腎評估、護理給藥核對、衛教紀錄與成效分析 |
| 七 | 護理給藥核對 | 病人身分＋藥品條碼比對醫囑、三讀五對、高警訊藥物雙人核對 |
| 八 | 多語言與無障礙 | 9 種語言卡片（臺語、客語規劃真人錄音）、語音朗讀、大字體、高對比，目標 WCAG 2.2 AA |
| 九 | 工程架構 | FastAPI 後端 API、HL7 FHIR `MedicationKnowledge` 端點、PWA 離線快取 |

## 專案結構

```
ai-medcare/
├── data/drugs.json          # 藥品知識庫（前後端共用）
├── frontend/
│   ├── app.src.html         # 前端原始碼（單檔、無需建置工具）
│   ├── index.html           # 建置後的 PWA 入口（由 build.js 產生）
│   ├── manifest.webmanifest # PWA 設定
│   ├── sw.js                # Service Worker 離線快取
│   └── icon.svg
├── backend/
│   ├── main.py              # FastAPI API ＋ 靜態檔案伺服
│   ├── requirements.txt
│   └── tests/test_api.py
├── build.js                 # 將 drugs.json 內嵌進前端
└── README.md
```

## 執行方式

```bash
# 1. 建置前端（修改 app.src.html 或 drugs.json 後執行）
node build.js

# 2. 啟動後端（同時提供前端頁面）
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- 前端：http://localhost:8000/ （手機與電腦在同一網路時，用電腦 IP 開啟即可測試；PWA 安裝與相機需 HTTPS）
- API 文件：http://localhost:8000/docs
- 測試：`python -m pytest backend/tests`

只看前端也可以直接用瀏覽器開啟 `frontend/index.html`。

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/health` | 系統狀態（含開發者 CY團隊） |
| GET | `/api/drugs?q=` | 藥品搜尋 |
| GET | `/api/drugs/{id}` | 藥品完整資料與衛教 |
| POST | `/api/match` | 外觀特徵 → Top-3 候選、相似藥警示、拒識判定 |
| POST | `/api/recognize` | 影像上傳（伺服器端模型預留介面） |
| POST | `/api/safety-check` | 用藥清單＋個人狀況 → 安全警示 |
| POST | `/api/chat` | RAG 衛教問答（含來源） |
| GET | `/fhir/MedicationKnowledge/{id}` | HL7 FHIR 格式，供 HIS／EMR 串接 |

## 邁向正式版

1. **資料**：改接食藥署許可證與仿單、健保署藥品代碼、政府資料開放平臺；藥物交互作用改用經授權的臨床藥學知識庫；每筆資料由藥師審核並記錄來源與更新日期。
2. **AI 模型**：YOLO 藥物偵測、EfficientNet／ViT 分類、PaddleOCR 刻痕與藥袋文字、ZXing 條碼、pgvector 相似藥搜尋；以 Accuracy、F1、Top-k、未知藥品拒識率評估。
3. **GenAI**：以本專案的檢索層作為 RAG context，生成限於來源內容，保留來源標示與藥師審核機制。
4. **平台**：Next.js 前端、PostgreSQL、Redis、OAuth 2.0＋RBAC、多租戶隔離、Docker／Kubernetes、TLS 與稽核紀錄。
5. **法規**：個資法、醫療法、醫療器材管理法（SaMD 判定）、ISO 14971、IEC 62304、ISO 27001。

---

© 2026 **CY團隊** 開發
