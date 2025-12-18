# Game Store System

一個 Python 實作的雙人對戰遊戲平台，採用微服務架構 (Microservices)，包含資料庫、開發者伺服器、大廳伺服器與客戶端。

## 系統架構
1. **DB Server (10195)**: 負責資料儲存與管理 (JSON)。
2. **Developer Server (10191)**: 處理開發者請求 (上架/更新/下架)，將檔案存入共享空間。
3. **Lobby Server (10192)**: 處理玩家請求 (大廳/房間)，啟動 Game Instance。
4. **Clients**: Developer Client (連線 10191) 與 Lobby Client (連線 10192)。

## 快速開始

### 1. 啟動所有 Server
使用 Launcher 一鍵啟動 DB, Dev, Lobby Server：
```bash
./start_system.sh
```
或手動啟動：
```bash
python3 server/db_server.py &
python3 server/dev_server.py &
python3 server/lobby_server.py &
```

### 2. 啟動客戶端
使用啟動腳本開啟 tmux 介面（包含 Server 與 Clients）：
```bash
./start_client.sh
```
或手動啟動：
*   **Developer Client**: `python3 client/developer_client.py`
*   **Lobby Client**: `python3 client/lobby_client.py`

## 內建遊戲：Snake Duel (snk)
本平台包含一個示範遊戲 `snk` (Snake Duel)，為雙人貪食蛇對戰。
*   **架構**: Server-Authoritative。
*   **介面**: `tkinter` GUI。
*   **特色**: 支援即時輸入同步、遊戲結束自動回報 Lobby。

## AI 遊戲生成
本系統支援使用 AI 生成相容的遊戲。請將 `GAME_GENERATION_CONFIG.yaml` 的內容提供給 LLM (如 ChatGPT)，它將能生成符合本平台 Protocol 的遊戲代碼。

**Protocol 重點**:
*   Port: 依賴 CLI Argument `--port`。
*   Room ID: 依賴 CLI Argument `--room_id`。
*   Lobby Port: 依賴 CLI Argument `--lobby_port` (預設 10192)。
*   Game Over Reporting: 遊戲結束時需透過 TCP 連線至 `127.0.0.1:<lobby_port>` 回報結果。

## 進階功能：Process Lifecycle Management
為了避免 Zombie Processes 與資源洩漏，系統實作了完整的生命週期管理：
1.  **Process Registry**: Lobby Server 維護 `running_games` 表，追蹤所有執行中的 Game Server 子程序。
2.  **Monitor Thread**: 背景執行緒每秒監控：
    *   **回收資源**: 對已結束的程序執行 `poll()` 與回收，防止殭屍程序。
    *   **崩潰偵測**: 若 Process 意外結束但沒回報結果，自動將房間重置為 `idle` 並通知玩家，避免狀態卡死。
3.  **Graceful Shutdown**: 當收到遊戲結果回報時，Server 主動等待子程序結束，確保留下乾淨的系統狀態。

## 評論系統 (Review System)
本平台提供完整的遊戲評價功能：
*   **撰寫評論**: 遊戲結束後，獲勝者與失敗者皆會收到彈出視窗，可進行 1-5 星評分並留下評語。
*   **查看評論**: 在商店 (Store) 或收藏庫 (Library) 中，點擊 "Details & Reviews" 按鈕即可查看該遊戲的詳細資訊、平均評分與玩家留言。
*   **資料儲存**: 所有評論皆持久化儲存於 `server_data/reviews.json`。

## 檔案結構
```
.
├── server/
│   ├── db_server.py    # 資料庫服務 (8880)
│   ├── dev_server.py   # 開發者服務 (8881)
│   ├── lobby_server.py # 大廳服務 (10192)
│   └── utils.py
├── client/
│   ├── developer_client.py
│   ├── lobby_client.py
│   └── web/            # Lobby Web GUI
├── snk/                # 內建貪食蛇遊戲
├── GAME_GENERATION_CONFIG.yaml # AI 遊戲生成配置
├── server_data/        # Server 資料庫
└── README.md
```

## 功能完成度
- [x] Server 資料持久化 (JSON, Auto-Reload on Restart)
- [x] Developer: Register, Login, Upload, Update, Delete
- [x] Player: Register, Login, List, Download, Create Room, Join Room
- [x] Review System: 評分、留言、查看評論 (UI Modal)
- [x] Game Execution: 自動 Fork/Subprocess 啟動, Robust Crash Handling
- [x] Game Template: 提供 Snake Duel 範例 (支援動態 Port 配置)
- [x] AI Generation Config: 標準化遊戲生成協定 (YAML)
