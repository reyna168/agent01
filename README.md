# agent01

Google Gemini Agentic Design Patterns 練習專案。

## 環境需求

- Windows
- Python 3.12
- Git

確認 Python 版本：

```powershell
py -3.12 --version
```

## 專案啟動步驟

### 1. 建立並啟用虛擬環境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

若出現「執行原則」錯誤，先執行一次：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. 安裝套件

```powershell
python -m pip install --upgrade pip
python -m pip install pydantic google-genai python-dotenv
```

### 3. 設定 API Key

建立 `.env` 檔（此檔不會上傳到 GitHub）：

```
GEMINI_API_KEY=你的金鑰
```

程式會透過 `python-dotenv` 讀取 `.env` 中的 `GEMINI_API_KEY`。

### 4. 執行程式

```powershell
python 03_gemini_agentic_design_patterns_python_code.py
```

## 程式重點

- `load_dotenv()` 從 `.env` 讀取 `GEMINI_API_KEY`
- 未設定金鑰時會直接報錯，避免使用空金鑰
- `generate_content_with_retry()` 遇到 `429` / `503` 會自動重試
- 重試失敗後依序切換備援模型：
  1. `gemini-2.5-flash`
  2. `gemini-2.5-flash-lite`
  3. `gemini-2.0-flash`

## Git / GitHub

第一次上傳：

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/reyna168/agent01.git
git push -u origin main
```

之後更新：

```powershell
git add .
git commit -m "更新說明"
git push
```

Git 身分設定：

```powershell
git config --global user.name "reyna168"
git config --global user.email "reyna0304@gmail.com"
```

## 注意事項

- `.env` 含 API Key，**不可**提交到 GitHub
- `.venv/`、`__pycache__/` 已被 `.gitignore` 排除
- 其他人 clone 後需自行建立 `.env` 並填入金鑰
