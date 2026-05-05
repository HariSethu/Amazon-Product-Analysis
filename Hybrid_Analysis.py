import pandas as pd
import numpy as np
import os, re, time
import threading
import sys
import concurrent.futures
import logging
from datasets import load_dataset
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Import Scraper and Brain modules
import Scraper
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# SETUP LOGGER
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # --- NEW: Added encoding='utf-8' here ---
        logging.FileHandler("app_tracker.log", encoding='utf-8'), 
        logging.StreamHandler(sys.stdout)                 
    ]
)
logger = logging.getLogger(__name__)

# Initialize vader sentiment analyzer
vader_analyzer = SentimentIntensityAnalyzer()

DEFAULT_DATASET_CATEGORIES = [
    "Electronics", "Cell_Phones_and_Accessories", "Video_Games",
    "Home_and_Kitchen", "Toys_and_Games", "All_Beauty",
    "Sports_and_Outdoors", "Automotive", "Tools_and_Home_Improvement"
]

_review_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 3600   # seconds before a cached result expires
CACHE_MAX  = 10    # max ASINs to hold in memory at once

def check_huggingface_dataset(category, asin, stop_event):
    """ Streams the Amazon Reviews 2023 dataset from Hugging Face by loading the JSONL file directly. """
    logger.info(f"Checking Hugging Face (Category: {category}) for {asin}...")

    file_name = f"{category}.jsonl"
    data_url = f"https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/review_categories/{file_name}"
    
    try:
        dataset = load_dataset("json", data_files=data_url, split="train", streaming=True)
        found_reviews = []
        max_search = 100000 
        count = 0
        
        for record in dataset:
            if stop_event.is_set():
                break

            count += 1
            if record.get('parent_asin') == asin:
                found_reviews.append({
                    'Rating': record.get('rating'),
                    'Text': record.get('text'),
                    'Date Posted': f"2023-Archived ({category})"
                })
            
            if len(found_reviews) >= 100:
                logger.info(f"[{category}] Found {len(found_reviews)} reviews! Signaling others to stop.")
                stop_event.set()
                break
            if count >= max_search:
                break

        if found_reviews:
            logger.info(f"Found {len(found_reviews)} reviews in '{category}' archived dataset!")
            return pd.DataFrame(found_reviews)
        else:
            return None

    except Exception as e:
        logger.error(f"Error streaming dataset for {category}: {e}")
        return None

def run_scraper_thread(asin):
    """ Separate function to run scraper in background thread """
    logger.info(f"Launching Chrome Live Scraper in Background...")

    try:
        driver = Scraper.setup_driver()
        url = f"https://www.amazon.com/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_sr?ie=UTF8&reviewerType=all_reviews&pageNumber=1"
        driver.get(url)

        product_filename = f"data/{asin}_live_reviews.csv"
        total_scraped = 0
        TARGET_PAGES = 5

        from selenium.webdriver.common.by import By

        for page in range(1, TARGET_PAGES + 1):
            logger.info(f"Scraping Page {page}/{TARGET_PAGES}...")
            count = Scraper.scrape_view(driver, asin, save_filename=product_filename)
            total_scraped += count
            
            if count == 0:
                break 
            
            if page < TARGET_PAGES:
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, "li.a-last a")
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3) 
                except:
                    logger.info("Reached end of live reviews.")
                    break
        driver.quit()

        if total_scraped > 0:
            df = pd.read_csv(product_filename, on_bad_lines='skip', engine='python')
            logger.info(f"✅ [Scraper] Finished! Pulled {len(df)} live reviews.")
            return df
        return None
    except Exception as e:
        logger.error(f"❌ [Scraper] Failed: {e}")
        return None
            
def gather_data_concurrently(asin):
    """ Gather data concurrently from Hugging Face Categories and Live Scraper simultaneously. """

    # Return cached result if still fresh — avoids re-scraping on keyword searches
    with _cache_lock:
        if asin in _review_cache:
            cached_time, cached_df = _review_cache[asin]
            if time.time() - cached_time < CACHE_TTL:
                logger.info(f"✅ Cache hit for {asin} — skipping re-fetch.")
                return cached_df.copy()
            del _review_cache[asin]

    logger.info(f"🚀 Launching {len(DEFAULT_DATASET_CATEGORIES)} Dataset Threads + 1 Scraper Thread concurrently...")

    stop_event = threading.Event()
    all_dataframes = []

    HF_TIMEOUT = 80  # seconds before giving up on dataset search

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(DEFAULT_DATASET_CATEGORIES) + 1) as executor:
        scraper_future = executor.submit(run_scraper_thread, asin)
        hf_futures = [executor.submit(check_huggingface_dataset, cat, asin, stop_event) for cat in DEFAULT_DATASET_CATEGORIES]

        # Wait for HuggingFace results with a hard cutoff
        try:
            for future in concurrent.futures.as_completed(hf_futures, timeout=HF_TIMEOUT):
                df = future.result()
                if df is not None and not df.empty:
                    all_dataframes.append(df)
                    total_collected = sum(len(d) for d in all_dataframes)
                    if total_collected >= 50:
                        stop_event.set()
                        break
        except concurrent.futures.TimeoutError:
            logger.warning(f"⏱️ HuggingFace search timed out after {HF_TIMEOUT}s — product not found in dataset. Falling back to live scraper.")
            stop_event.set()

        # Always collect scraper result (has been running in parallel the whole time)
        try:
            scraper_df = scraper_future.result(timeout=300)
            if scraper_df is not None and not scraper_df.empty:
                all_dataframes.append(scraper_df)
        except concurrent.futures.TimeoutError:
            logger.error("Live scraper also timed out.")

    if not all_dataframes:
        return None

    result = pd.concat(all_dataframes, ignore_index=True)

    # Store in cache, evicting the oldest entry if at capacity
    with _cache_lock:
        if len(_review_cache) >= CACHE_MAX:
            oldest = min(_review_cache, key=lambda k: _review_cache[k][0])
            del _review_cache[oldest]
        _review_cache[asin] = (time.time(), result)

    return result

def analyze_aspects(df):
    """ Performs ABSA using VADER with synonym grouping. """
    
    # 1. The Master Dictionary: Grouping aspects with related keywords
    aspect_map = {
        "price & value": ["price", "cost", "money", "value", "expensive", "cheap", "worth", "affordable"],
        "quality & build": ["quality", "build", "material", "sturdy", "flimsy", "broke", "solid", "plastic"],
        "usability & setup": ["easy", "hard", "intuitive", "setup", "install", "instructions", "use"],
        "durability": ["lasts", "broke", "wear", "tear", "durable", "longevity", "reliable"],
        "customer service": ["service", "warranty", "return", "shipping", "support", "refund"],
        "ergonomics & comfort": ["comfortable", "heavy", "light", "weight", "grip", "feel", "hurts", "fit"],
        "performance": ["fast", "slow", "powerful", "weak", "performance", "lag", "responsive"],
        "battery & power": ["battery", "charge", "power", "life", "plug"],
        "display & screen": ["screen", "display", "bright", "color", "resolution"],
        "audio & noise": ["sound", "audio", "loud", "quiet", "noisy", "bass"],        
        "connectivity": ["bluetooth", "wifi", "drops", "signal", "disconnects", "pairs"]
    }

    # Initialize a dictionary to hold scores for the main aspect categories
    aspect_scores = {main_aspect: [] for main_aspect in aspect_map.keys()}
    
    for text in df['Text'].dropna():
        # Split review into sentences
        sentences = re.split(r'[.!?]', str(text))
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # 2. Check if ANY of the synonyms are in the sentence
            for main_aspect, keywords in aspect_map.items():
                if any(keyword in sentence_lower for keyword in keywords):
                    
                    # Calculate VADER score
                    compound_score = vader_analyzer.polarity_scores(sentence)['compound']
                    
                    # Convert the -1.0 to 1.0 scale into a 1 to 5 star scale
                    normalized_score = ((compound_score + 1) / 2) * 4 + 1
                    aspect_scores[main_aspect].append(normalized_score)

    # 3. Format the final output
    final_report = {}
    for aspect, scores in aspect_scores.items():
        # Only include aspects that have a meaningful amount of mentions (e.g., >= 2)
        if len(scores) >= 2:
            avg_score = sum(scores) / len(scores)
            
            if avg_score >= 4.0: label = "Excellent"
            elif avg_score >= 3.0: label = "Average"
            else: label = "Poor"
            
            final_report[aspect] = {
                "score": round(avg_score, 1),
                "label": label,
                "mentions": len(scores)
            }
            
    # 4. Sort results by most mentioned so the UI prioritizes the biggest talking points
    sorted_report = dict(sorted(final_report.items(), key=lambda item: item[1]['mentions'], reverse=True))
            
    return sorted_report


def ask_questions(df):
    """ Simple keyword-based Q&A system to explore what people say about specific aspects. """
    logger.info("\n💬 ASK THE REVIEWS:")
    logger.info("Type a keyword (e.g., 'battery', 'screen', 'price') to see what people say.")
    logger.info("Type 'back' to choose a new product.")
    
    df['Text_Lower'] = df['Text'].astype(str).str.lower()
    
    while True:
        # Note: input() is kept as it's required for user interaction, not a log event.
        query = input("\n❓ Question/Keyword: ").strip().lower()
        
        if query in ['back', 'exit', 'quit']:
            break
            
        matches = df[df['Text_Lower'].str.contains(query, na=False)]
        
        if matches.empty:
            logger.warning(f"No reviews mentioned '{query}'.")
            continue
            
        avg_match_rating = matches['Rating'].mean()
        sentiment = "Positive" if avg_match_rating > 3.5 else "Negative" if avg_match_rating < 2.5 else "Mixed"
        
        logger.info(f"🔎 Found {len(matches)} reviews mentioning '{query}'.")
        logger.info(f"⭐️ Context Rating: {avg_match_rating:.1f}/5.0 ({sentiment})")
        logger.info("-" * 30)
        
        logger.info("🗣️  WHAT PEOPLE SAY:")
        for text in matches['Text'].head(3):
            sentences = re.split(r'[.!?]', str(text))
            for s in sentences:
                if query in s.lower():
                    logger.info(f" - \"...{s.strip()}...\"")
                    break
        logger.info("-" * 30)

def main():
    while True:
        # standard print for UI separation is fine, but logger works too
        print("\n" + "="*60)
        user_input = input("Enter Amazon Link/ASIN (or 'q' to quit): ").strip()
        
        if user_input.lower() in ['q', 'quit']:
            break

        asin_match = re.search(r'(B0[A-Z0-9]{8})', user_input)
        if asin_match:
            asin = asin_match.group(1)
            logger.info(f"Target ASIN: {asin}")
        else:
            logger.warning("Invalid Link/ASIN.")
            continue

        start_time = time.time()
        
        df = gather_data_concurrently(asin)
        
        duration = time.time() - start_time

        if df is not None and not df.empty:
            logger.info(f"✅ DATA AGGREGATED: {len(df)} total reviews found in {duration:.1f} seconds!")
            analyze_aspects(df)  # Changed to the new ABSA function
            ask_questions(df)
        else:
            logger.warning(f"❌ No reviews found anywhere after {duration:.1f} seconds.")

if __name__ == "__main__":
    main()