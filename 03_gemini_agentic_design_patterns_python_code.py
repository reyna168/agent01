"""
Lesson 03 - Agentic Design Patterns (使用 Google Gemini API)

本程式碼示範三個 foundational design patterns：
1. Clear Agent Instructions (明確的 Agent 指令與 System Instruction)
2. Structured Output with Pydantic Models (使用 Pydantic 模型實現結構化 JSON 輸出)
3. Single Responsibility Agents (單一職責 Agents 與工具調用 Workflow)
"""

import os
import time
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import errors, types

# 1. 從 .env 讀取 GEMINI_API_KEY 並初始化 Google GenAI Client
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("找不到 GEMINI_API_KEY，請在 .env 或環境變數中設定")
client = genai.Client(api_key=api_key)

# 模型忙碌 (503) 時依序改用備援模型
MODEL_NAMES = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

MAX_RETRIES = 3


def generate_content_with_retry(contents, config=None):
    """遇到 429/503 時自動重試並切換備援模型。"""
    last_error = None
    for model_name in MODEL_NAMES:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except errors.APIError as e:
                last_error = e
                if getattr(e, "code", None) in (429, 503):
                    print(f"[{model_name}] 伺服器忙碌 ({e.code})，第 {attempt} 次重試...")
                    time.sleep(2 ** attempt)
                    continue
                raise
    raise last_error


# ==========================================
# Pattern 2 所需的 Pydantic 模型與 Tool 定義
# ==========================================

class DestinationRecommendation(BaseModel):
    destination: str = Field(description="目的地名稱")
    available: bool = Field(description="是否有空房/是否可預訂")
    best_season: str = Field(description="最佳旅遊季節")
    highlights: List[str] = Field(description="景點或特色亮點")
    estimated_budget_usd: int = Field(description="估算預算 (USD)")


class TravelRecommendations(BaseModel):
    recommendations: List[DestinationRecommendation]
    personalized_note: str = Field(description="給旅客的個人化建議短語")


def get_destination_details(destination: str) -> dict:
    """獲取度假目的地的結構化詳細資訊。

    Args:
        destination: 要查詢的目的地名稱 (如 Barcelona, Tokyo, Cape Town)
    """
    details = {
        "Barcelona": {
            "destination": "Barcelona",
            "available": True,
            "best_season": "May-Jun",
            "highlights": ["Beach", "Architecture", "Nightlife"],
            "estimated_budget_usd": 2000,
        },
        "Tokyo": {
            "destination": "Tokyo",
            "available": True,
            "best_season": "Mar-Apr",
            "highlights": ["Culture", "Food", "Technology"],
            "estimated_budget_usd": 2500,
        },
        "Cape Town": {
            "destination": "Cape Town",
            "available": False,
            "best_season": "Nov-Mar",
            "highlights": ["Nature", "Wine", "Adventure"],
            "estimated_budget_usd": 1800,
        },
    }
    return details.get(
        destination,
        {
            "destination": destination,
            "available": False,
            "best_season": "Unknown",
            "highlights": [],
            "estimated_budget_usd": 0,
        },
    )


# ==========================================
# 核心執行流程
# ==========================================

def run_pattern_1():
    print("==========================================")
    print("Pattern 1: Clear Agent Instructions")
    print("==========================================")
    
    system_instruction = """你是一位名為 Alex 的奢華旅遊顧問。你的職責是：
1. 理解旅客的偏好（預算、氣候、活動類型）
2. 在做出推薦前先確認目的地的可用性/空房狀況
3. 提供詳細且個人化的旅遊建議
4. 務必提及簽證要求與最佳旅遊季節

保持熱情、專業且對旅遊充滿熱忱。"""

    response = generate_content_with_retry(
        contents="我想去一個擁有豐富美食和歷史的地方度過一週假期，預算大約是 2,500 美元。",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
        ),
    )
    
    print(response.text)
    print("\n")


def run_pattern_2():
    print("==========================================")
    print("Pattern 2: Structured Output with Pydantic Models")
    print("==========================================")
    
    # 使用 response_mime_type 與 response_schema 強制 Gemini 輸出強型別結構化資料
    config = types.GenerateContentConfig(
        system_instruction="你是一位旅遊專家。請根據旅客偏好推薦目的地並填寫結構化欄位。",
        response_mime_type="application/json",
        response_schema=TravelRecommendations,
        temperature=0.2,
    )

    response = generate_content_with_retry(
        contents="為一位喜愛文化且預算為 2,500 美元的旅客推薦 3 個目的地（包含 Barcelona, Tokyo, Cape Town）。",
        config=config,
    )

    # 透過 response.parsed 自動反序列化為 Pydantic 物件
    result: TravelRecommendations = response.parsed

    for rec in result.recommendations:
        status = "可預訂（Available）" if rec.available else "不可預訂（Not available）"
        print(f"{rec.destination} ({status})")
        print(f"  最佳季節: {rec.best_season}")
        print(f"  亮點特色: {', '.join(rec.highlights)}")
        print(f"  預估預算: ${rec.estimated_budget_usd}")
        print()
    print(f"備註: {result.personalized_note}")
    print("\n")


def run_pattern_3():
    print("==========================================")
    print("Pattern 3: Single Responsibility Agents")
    print("==========================================")

    # Agent 1: 目的地專家 (配備工具查詢)
    dest_instructions = """你是一位目的地研究專家。你的唯一任務是：
1. 根據旅客偏好評估目的地
2. 使用提供的工具 get_destination_details 檢查目的地資訊與可用性
3. 返回一份簡短的排名清單並列出優缺點

請勿討論航班、飯店或物流規劃 — 另有 Agent 負責該領域。"""

    dest_config = types.GenerateContentConfig(
        system_instruction=dest_instructions,
        tools=[get_destination_details],  # 啟用 Function Calling
        temperature=0.3,
    )

    print("--- 步驟 1: 目的地專家 (Destination Expert) 運作中 ---")
    dest_response = generate_content_with_retry(
        contents="我想去一個預算在 2,500 美元以下、擁有豐富文化與美食的地方度過一週。請幫我評估 Tokyo, Barcelona, Cape Town 哪裡適合？",
        config=dest_config,
    )
    print(dest_response.text)
    print("\n")

    # Agent 2: 物流與行程規劃師
    logistics_instructions = """你是一位旅遊物流與行程規劃師。你的唯一任務是：
1. 為選定的目的地制定逐日行程規劃
2. 在預算範圍內提供航班與飯店選項建議
3. 註明簽證要求與旅遊保險建議

請勿推薦目的地 — 另有 Agent 負責該領域。"""

    logistics_config = types.GenerateContentConfig(
        system_instruction=logistics_instructions,
        temperature=0.5,
    )

    print("--- 步驟 2: 物流與行程規劃師 (Logistics Planner) 運作中 ---")
    logistics_response = generate_content_with_retry(
        contents=f"根據以下前一階段的推薦內容，為旅客規劃為期一週的詳細行程：\n\n{dest_response.text}",
        config=logistics_config,
    )
    print(logistics_response.text)


if __name__ == "__main__":
    # 執行三個設計模式的範例
    run_pattern_1()
    run_pattern_2()
    run_pattern_3()