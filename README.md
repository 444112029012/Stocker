# Stocker

本機台股情報機器人：追蹤公開資訊觀測站重大訊息、投信買賣超，以及規模前五大主動式 ETF 的持股加減碼，整理後推到 Telegram。

## GitHub Actions 能不能在電腦關機時跑？

**可以執行，但第一版不適合。** GitHub Actions 跑在 GitHub 的雲端機器上，你的電腦關機沒關係。不過每次工作流程都是一台全新虛擬機：

- 本機 SQLite（已推播紀錄、昨日持股）預設不會留下來
- 免費額度有限，盤中每 20 分鐘拉一次重訊會很快用完
- 排程可能延遲數分鐘到數十分鐘

所以第一版做成**本機常駐**：電腦要開著（或睡眠不要斷電到程式被殺掉）。之後若要雲端 24 小時跑，需要外接資料庫（例如 SQLite 同步到雲端、或 Turso / PostgreSQL）再接到 Actions 或小 VPS。

## 會推什麼

| 時間（台北） | 內容 |
|---|---|
| 平日 08:00–17:40 每 20 分鐘 | 全市場**高重要性**重大訊息（減資、併購、庫藏股、停工、董總異動等） |
| 平日 21:30 | 每日摘要：重要重訊、投信買賣超 Top 10、主動 ETF **共識排行**（同步檔數越多越前面） |

預設追蹤的主動式 ETF（依近期規模前五大，可在 `stocker/settings.py` 改）：

1. 00981A 主動統一台股增長  
2. 00403A 主動統一升級50  
3. 00991A 主動復華未來50  
4. 00988A 主動統一全球創新  
5. 00982A 主動群益台灣強棒  

**第一次跑只會存下今日持股。** 隔一個交易日才能看到實際買賣超（股票、張數、權重）。張數是兩個持股日快照相減，不是交易所逐筆成交。

資料來源為證交所／櫃買 OpenAPI，以及各投信官網公開的投資組合／申購買回清單。非正式投資建議。

## 安裝（Windows）

1. 安裝 [Python 3.12+](https://www.python.org/downloads/)，安裝時勾選 Add Python to PATH。
2. 在專案目錄開啟 PowerShell：

```powershell
cd D:\Stocker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

3. 建立 Telegram 機器人
   - 在 Telegram 找 `@BotFather`，送 `/newbot`，取得 token
   - 對你的機器人傳一句話（例如 `hi`）
   - 瀏覽器打開：`https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 在 JSON 裡找 `"chat":{"id": 數字}`，那就是 chat_id
4. 編輯 `.env`：

```
TELEGRAM_BOT_TOKEN=你的token
TELEGRAM_CHAT_ID=你的chat_id
```

5. 先測通道，再手動跑一次摘要：

```powershell
python -m stocker test
python -m stocker daily --print-only
python -m stocker daily
```

6. 開始常駐（會送出主選單按鈕）：

```powershell
python -m stocker run
```

或雙擊 `run.bat`。視窗不要關。Telegram 下方會出現：

- **立即推播**：馬上送每日摘要  
- **ETF加減碼**：多檔同步加減碼共識排行（含比較的兩個交易日）  
- **立刻抓重訊**：只送還沒推過的高重要性訊息  
- **測試連線** / **使用說明**

也可直接打 `/start`、`/daily`、`/etf`、`/mops`。

### 開機自動跑（工作排程器）

1. 開啟「工作排程器」→ 建立工作
2. 觸發程序：登入時
3. 動作：啟動程式  
   - 程式：`D:\Stocker\.venv\Scripts\python.exe`  
   - 引數：`-m stocker run`  
   - 起始於：`D:\Stocker`
4. 設定：勾選「工作正在執行時仍立即執行新執行個體」可關掉；電腦睡眠可能會暫停，建議插電並關閉睡眠，或只在你平常開機時跑。

## 指令

```text
python -m stocker test          # Telegram 測試（並叫出主選單）
python -m stocker mops          # 立刻抓高重要性重訊
python -m stocker daily         # 立刻推每日摘要
python -m stocker daily --print-only
python -m stocker etf           # 主動 ETF 共識排行
python -m stocker etf --print-only
python -m stocker run           # 常駐排程 + Telegram 主選單
```

## 專案結構

```text
stocker/
  collectors/     # MOPS、投信 T86、主動 ETF 持股
  intelligence/   # 重訊評分、持股 diff、摘要格式
  notifiers/      # Telegram
  jobs.py
  scheduler.py
data/stocker.db   # 去重與歷史持股（執行後產生）
```
