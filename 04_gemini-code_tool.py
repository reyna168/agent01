"""Lesson 04 - Tool Use Design Pattern (Gemini Model Edition)

This script demonstrates how to implement tool use, structured Pydantic outputs, 
and human-in-the-loop approval patterns with Google's Gemini model using the 
`google-genai` SDK.

Requirements:
    %pip install google-genai pydantic python-dotenv -U -q
"""

import os
import time
from typing import Annotated, Any, Callable, get_type_hints
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

# 1. Environment and Client Setup
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError(
        "Missing required environment variable: GEMINI_API_KEY. "
        "Please set it in your .env file or shell environment."
    )

# Initialize the official Gemini client
client = genai.Client(api_key=api_key)
# gemini-2.5-flash 免費額度用完時可改用 gemini-2.5-flash-lite
MODEL_ID = "gemini-2.5-flash-lite"  # Use your preferred Gemini model


def call_with_retry(func, *args, max_retries=4, **kwargs):
    """遇到 429/503 時自動指數退避重試。"""
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except errors.APIError as e:
            if getattr(e, "code", None) in (429, 503) and attempt < max_retries:
                print(f"伺服器忙碌 ({e.code})，第 {attempt} 次重試...")
                time.sleep(2 ** attempt)
                continue
            raise


# =====================================================================
# 2. Defining Tools (Custom Decorator Pattern mimicking @tool)
# =====================================================================
# In the google-genai SDK, standard Python functions with type hints 
# and docstrings can be passed directly as tools. We can create a lightweight 
# decorator or metadata wrapper to handle approval modes if needed.

def tool(approval_mode: str = "never_require"):
    """Decorator to attach metadata like approval_mode to Python functions."""
    def decorator(func: Callable):
        func.approval_mode = approval_mode
        return func
    return decorator


@tool(approval_mode="never_require")
def get_destinations() -> list[str]:
    """Get available vacation destinations."""
    return ["Barcelona", "Paris", "Berlin", "Tokyo", "Sydney", "New York City"]


@tool(approval_mode="never_require")
def check_availability(
    destination: Annotated[str, "The destination to check"],
) -> str:
    """Check booking availability for a destination."""
    availability = {
        "Barcelona": "Available - 3 spots left",
        "Paris": "Available",
        "Berlin": "Sold out",
        "Tokyo": "Available - 1 spot left",
        "Sydney": "Available",
        "New York City": "Available",
    }
    return availability.get(destination, "Unknown destination")


@tool(approval_mode="never_require")
def get_flight_info(
    origin: Annotated[str, "Origin airport code"],
    destination: Annotated[str, "Destination airport code"],
) -> str:
    """Get flight information between two cities."""
    flights = {
        "LHR-BCN": "BA 2042, Departs 08:30, Arrives 11:45, $350",
        "LHR-CDG": "AF 1081, Departs 09:15, Arrives 11:30, $280",
        "LHR-NRT": "JL 044, Departs 11:00, Arrives 07:00+1, $890",
    }
    return flights.get(
        f"{origin}-{destination}",
        f"No direct flights from {origin} to {destination}",
    )


@tool(approval_mode="always_require")
def book_flight(
    origin: Annotated[str, "Origin airport code"],
    destination: Annotated[str, "Destination airport code"],
    passenger_name: Annotated[str, "Full name of the passenger"],
) -> str:
    """Book a flight for a passenger. Requires approval before executing."""
    return (
        f"Flight booked from {origin} to {destination} "
        f"for {passenger_name}. Confirmation #TRV-2026-{hash(passenger_name) % 10000:04d}"
    )


# Bundle tools into a convenient lookup dictionary
travel_tools = [get_destinations, check_availability, get_flight_info, book_flight]
tool_map = {t.__name__: t for t in travel_tools}


# =====================================================================
# 3. Running Multi-Tool Agent Tasks with Gemini
# =====================================================================
def run_basic_travel_query():
    print("--- 1. Running Standard Multi-Tool Query ---")
    prompt = "What destinations do you have? Which ones are still available?"
    
    response = call_with_retry(
        client.models.generate_content,
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=travel_tools,
            temperature=0.0,
        ),
    )
    print(response.text)
    print("\n" + "="*50 + "\n")


# =====================================================================
# 4. Structured Output with Pydantic Models
# =====================================================================
class BookingRecommendation(BaseModel):
    destination: str
    available: bool
    flight_details: str
    estimated_cost: int


class TravelPlan(BaseModel):
    recommendations: list[BookingRecommendation]


def run_structured_output_query():
    print("--- 2. Running Structured Output Query (Pydantic) ---")
    prompt = (
        "I want to fly from London Heathrow to somewhere warm in Europe. "
        "Check what's available and provide recommendations."
    )

    # Gemini 不支援同時使用 tools 與 response_mime_type="application/json"，
    # 因此先呼叫工具取得真實資料，再單獨要求結構化輸出（同 Lesson 03 Pattern 2）。
    chat = client.chats.create(
        model=MODEL_ID,
        config=types.GenerateContentConfig(
            tools=travel_tools,
            temperature=0.0,
        ),
    )
    tool_response = call_with_retry(chat.send_message, prompt)

    response = call_with_retry(
        client.models.generate_content,
        model=MODEL_ID,
        contents=(
            "請根據以下查詢結果整理旅遊建議，並輸出結構化資料：\n\n"
            f"{tool_response.text}"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TravelPlan,
            temperature=0.0,
        ),
    )
    
    # Parse the JSON string back into our Pydantic model
    plan = TravelPlan.model_validate_json(response.text)
    for rec in plan.recommendations:
        status = "available" if rec.available else "unavailable"
        print(
            f"{rec.destination}: {status} | "
            f"{rec.flight_details} (~${rec.estimated_cost})"
        )
    print("\n" + "="*50 + "\n")


# =====================================================================
# 5. Tool Approval Pattern Implementation (Human-in-the-Loop)
# =====================================================================
def run_approval_pattern_demo():
    print("--- 3. Demonstrating Tool Approval Pattern ---")
    
    # Inspect tool properties defined via decorator
    for tool_func in travel_tools:
        mode = getattr(tool_func, "approval_mode", "never_require")
        print(f"Tool name: {tool_func.__name__} | Approval mode: {mode}")

    print("\nSimulating execution request for 'book_flight':")
    target_tool = book_flight
    if getattr(target_tool, "approval_mode") == "always_require":
        print(f"🔒 [SECURITY] Tool '{target_tool.__name__}' requires human approval before execution.")
        # Simulated user approval check
        user_approved = True  
        if user_approved:
            result = target_tool(origin="LHR", destination="BCN", passenger_name="Alice Smith")
            print(f"✅ Execution result: {result}")
        else:
            print("❌ Tool execution cancelled by user.")


if __name__ == "__main__":
    run_basic_travel_query()
    run_structured_output_query()
    run_approval_pattern_demo()