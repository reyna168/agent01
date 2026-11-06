"""
Finding the Cheapest Airbnb with AI-Powered Web Automation (Gemini Edition)

This script automates searching Airbnb, extracting listing prices, and finding the cheapest option in Stockholm
using Playwright, Browser-Use, and Google Gemini (via langchain-google-genai).
"""

import asyncio
import os
import sys
import base64
import shutil
import tempfile
import subprocess
import traceback
import aiohttp
from typing import Optional, List
from dotenv import load_dotenv

# Playwright imports
from playwright.async_api import async_playwright

# Browser-Use & Google Gemini imports
from browser_use import Agent, Browser, ChatGoogle
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Google Gemini Configuration
gemini_api_key = os.getenv("GEMINI_API_KEY")
gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

print("✅ Google Gemini Configuration:")
print(f"   Model: {gemini_model_name}")
print(f"   API Key Status: {'Loaded' if gemini_api_key else 'Missing (Please set GEMINI_API_KEY in .env)'}")

if not gemini_api_key:
    print("❌ Error: GEMINI_API_KEY environment variable is not set. Please add it to your .env file or environment.")
    sys.exit(1)

# Initialize Google Gemini with Browser-Use's native ChatGoogle integration
llm = ChatGoogle(
    model=gemini_model_name,
    api_key=gemini_api_key,
    temperature=0.3
)
print("✅ LLM initialized successfully")


# --- Structured Output Models ---
class AirbnbListing(BaseModel):
    """Single Airbnb listing with price information"""
    title: str = Field(description="Name/title of the listing")
    price_per_night: float = Field(
        description="Price per night as a number (extract just the numeric value, ignore currency symbols)")
    currency: str = Field(
        default="SEK", description="Currency code (SEK for Swedish Krona)")
    rating: Optional[float] = Field(
        default=None, description="Rating score if visible")
    url: Optional[str] = Field(
        default=None, description="Full URL link to the listing page")


class SearchResult(BaseModel):
    """Complete search results from Airbnb"""
    location: str = Field(description="Search location (Stockholm, Sweden)")
    total_listings_found: int = Field(
        description="Number of listings found on the page")
    listings: List[AirbnbListing] = Field(
        description="List of all listings with prices extracted from the page")
    cheapest_listing: AirbnbListing = Field(
        description="The listing with the lowest price per night")
    average_price: float = Field(
        description="Average price per night across all listings")
    price_range: str = Field(description="Price range as 'min - max SEK'")


# --- Console Logging & Display Helpers ---
def log_step(step_number: int, title: str, description: str):
    print(f"\n{'='*60}")
    print(f"📍 Step {step_number}: {title}")
    print(f"   {description}")
    print(f"{'='*60}\n")


def log_action(action_type: str, details: str, emoji: str = "⚙️"):
    print(f"{emoji} [{action_type}] {details}")


def log_result(success: bool, message: str):
    emoji = "✅" if success else "❌"
    print(f"{emoji} {message}\n")


# --- Agent Class ---
class AirbnbSearchAgent:
    """
    Intelligent Airbnb search agent using Browser-Use integration via CDP.
    """

    def __init__(self, llm, cdp_url: str):
        self.llm = llm
        self.browser = Browser(
            cdp_url=cdp_url,
            keep_alive=True
        )

    async def search_stockholm(self) -> SearchResult:
        log_step(
            1,
            "Navigate & Search (AI Agent)",
            "Using AI agent with Gemini vision to navigate Airbnb and search for Stockholm listings."
        )

        try:
            search_agent = Agent(
                task=(
                    "Navigate to https://www.airbnb.com. "
                    "Close any pop-ups, cookie banners, or login prompts if they appear. "
                    "Search for 'Stockholm, Sweden' in the search box. "
                    "Wait for the search results page to fully load with listing cards visible."
                ),
                llm=self.llm,
                browser=self.browser,
                use_vision=True
            )

            log_action("Agent", "Navigating to Airbnb and searching for Stockholm...")
            await search_agent.run()
            await asyncio.sleep(3)
            log_result(True, "Successfully loaded Stockholm search results")

        except Exception as e:
            log_result(False, f"Search failed: {str(e)}")
            raise

        log_step(
            2,
            "Extract Prices (Vision + Gemini LLM)",
            "Using Gemini Vision to read all listing prices from the page and extract structured data."
        )

        try:
            pages = await self.browser.get_pages()
            if not pages:
                raise RuntimeError("No pages available after Agent run. Browser might have closed.")

            page = pages[0]
            log_action("Vision", "Gemini AI is analyzing the page and reading prices...")

            extraction_prompt = """
Extract ALL Airbnb Home listings visible on this page. DO NOT include "Experiences" or other non-home listings.

For each listing, extract:
- Title/name of the property
- Price per night (numeric value only, without currency symbols)
- Currency (SEK for Swedish Krona)
- Rating if visible
- URL: The full link to the listing detail page (should start with https://www.airbnb.com/rooms/)

After extracting all listings:
- Identify which listing has the LOWEST price
- Calculate the average price across all listings
- Determine the price range (min to max)

Focus on the listing cards on the search results page.
Only include listings where you can clearly see the price.
IMPORTANT: Extract the actual URL/link for each listing so users can click on it.
"""

            search_results = await page.extract_content(
                prompt=extraction_prompt,
                structured_output=SearchResult,
                llm=self.llm
            )

            log_action("Extracted", f"Found {search_results.total_listings_found} listings with prices")

            if len(search_results.listings) > 0:
                sample_prices = [f"{l.price_per_night:.0f} SEK" for l in search_results.listings[:5]]
                log_action("Sample Prices", f"{', '.join(sample_prices)}{'...' if len(search_results.listings) > 5 else ''}")

            log_result(True, "Price extraction completed successfully")
            return search_results

        except Exception as e:
            log_result(False, f"Price extraction failed: {str(e)}")
            raise


# --- Chrome CDP Launcher ---
async def start_chrome_with_cdp(port: int = 9222):
    user_data_dir = tempfile.mkdtemp(prefix='chrome_cdp_')
    chrome_paths = []

    custom_path = os.getenv('CHROME_PATH')
    if custom_path:
        chrome_paths.append(custom_path)

    if sys.platform == 'win32':
        for env_var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(env_var)
            if not base:
                continue
            chrome_paths.extend([
                os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(base, 'Google', 'Chrome Beta', 'Application', 'chrome.exe'),
                os.path.join(base, 'Google', 'Chrome Dev', 'Application', 'chrome.exe'),
                os.path.join(base, 'Google', 'Chrome SxS', 'Application', 'chrome.exe'),
                os.path.join(base, 'Chromium', 'Application', 'chrome.exe'),
            ])
    elif sys.platform == 'darwin':
        chrome_paths.extend([
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
        ])
    else:
        chrome_paths.extend([
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/snap/bin/chromium',
        ])

    for name in ('chrome', 'google-chrome', 'chromium', 'chromium-browser'):
        found = shutil.which(name)
        if found:
            chrome_paths.append(found)

    chrome_exe = None
    seen = set()
    for path in chrome_paths:
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        try:
            test_proc = await asyncio.create_subprocess_exec(
                path, '--version',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            await test_proc.wait()
            chrome_exe = path
            break
        except Exception:
            continue

    if not chrome_exe:
        raise RuntimeError(
            '❌ Chrome/Chromium executable not found. Please install Google Chrome '
            'or set the CHROME_PATH environment variable to chrome.exe.'
        )

    cmd = [
        chrome_exe,
        f'--remote-debugging-port={port}',
        f'--user-data-dir={user_data_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        'about:blank',
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    cdp_ready = False
    for _ in range(20):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://localhost:{port}/json/version',
                    timeout=aiohttp.ClientTimeout(total=1)
                ) as response:
                    if response.status == 200:
                        cdp_ready = True
                        break
        except Exception:
            pass
        await asyncio.sleep(1)

    if not cdp_ready:
        process.terminate()
        raise RuntimeError('❌ Chrome failed to start with CDP interface')

    print(f"✅ Chrome started with CDP on port {port}")
    return process


# --- Main Runner ---
async def main():
    print("🏠 Starting Stockholm Airbnb Price Finder (Gemini Powered)")

    chrome_process = None
    playwright_browser = None
    playwright = None
    agent = None

    try:
        log_action("Chrome", "Starting Chrome with CDP (remote debugging)...")
        chrome_process = await start_chrome_with_cdp(port=9222)
        cdp_url = 'http://localhost:9222'

        log_action("Playwright", "Connecting Playwright to Chrome via CDP...")
        playwright = await async_playwright().start()
        playwright_browser = await playwright.chromium.connect_over_cdp(cdp_url)
        log_result(True, "Playwright connected successfully")

        log_action("Browser-Use", "Creating Browser-Use agent with Gemini model...")
        agent = AirbnbSearchAgent(llm=llm, cdp_url=cdp_url)
        log_result(True, "Agent initialized with Gemini integration")

        result = await agent.search_stockholm()

        # Display Final Summary
        print("\n" + "="*60)
        print("📊 SEARCH RESULTS SUMMARY")
        print("="*60)
        print(f"📍 Location:             {result.location}")
        print(f"🏠 Total Listings Found: {result.total_listings_found}")
        print(f"💵 Average Price:        {result.average_price:.2f} SEK/night")
        print(f"📈 Price Range:          {result.price_range}")
        print("-" * 60)

        cheapest = result.cheapest_listing
        savings = result.average_price - cheapest.price_per_night
        print("🏆 CHEAPEST AIRBNB LISTING:")
        print(f"   Title:   {cheapest.title}")
        print(f"   Price:   {cheapest.price_per_night:.2f} {cheapest.currency}/night")
        if cheapest.rating:
            print(f"   Rating:  ⭐ {cheapest.rating}/5.0")
        print(f"   Savings: 💰 {savings:.2f} SEK cheaper than average")
        if cheapest.url:
            print(f"   Link:    🔗 {cheapest.url}")
        print("="*60)

        if len(result.listings) > 1:
            print("\n📋 ALL LISTINGS RANKED BY PRICE:")
            sorted_listings = sorted(result.listings, key=lambda x: x.price_per_night)
            for idx, listing in enumerate(sorted_listings, 1):
                badge = "🏆 " if listing.price_per_night == cheapest.price_per_night else "   "
                rating_str = f"⭐ {listing.rating}" if listing.rating else "N/A"
                print(f"{badge}{idx:2d}. {listing.title[:45]:<45} | {listing.price_per_night:7.2f} {listing.currency} | Rating: {rating_str}")
                if listing.url:
                    print(f"        Link: {listing.url}")

        log_result(True, "Price comparison completed successfully!")

    except Exception as e:
        log_result(False, f"Error during search: {str(e)}")
        print(traceback.format_exc())

    finally:
        log_action("Cleanup", "Closing browser and cleaning up processes...")
        if agent and getattr(agent, 'browser', None):
            try:
                await agent.browser.close()
            except Exception:
                pass

        if playwright_browser:
            try:
                await playwright_browser.close()
            except Exception:
                pass

        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass

        if chrome_process:
            chrome_process.terminate()
            try:
                await asyncio.wait_for(chrome_process.wait(), 5)
            except (asyncio.TimeoutError, TimeoutError):
                chrome_process.kill()

        log_result(True, "Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
