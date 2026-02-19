import pandas as pd
import tensorflow as tf
import numpy as np
import os, re, time
from datasets import load_dataset

# Import Scraper and Brain modules
import Scraper
import sentiment_brain

DEFAULT_DATASET_CATEGORY = "Electronics"

#First check Hugging Face Dataset, then fallback to Scraper if not found. Finally, analyze sentiment and allow Q&A.
def check_huggingface_dataset(asin):
    """
    Streams the Amazon Reviews 2023 dataset from Hugging Face by loading the JSONL file directly.
    """
    print(f"   Checking Hugging Face (Category: {DEFAULT_DATASET_CATEGORY}) for {asin}...")
    
    file_name = f"{DEFAULT_DATASET_CATEGORY}.jsonl"
    data_url = f"https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/review_categories/{file_name}"
    
    try:
        dataset = load_dataset("json", data_files=data_url, split="train", streaming=True)
        found_reviews = []
        max_search = 100000 
        count = 0

        print("   Streaming data... (Press Ctrl+C to skip)")
        
        for record in dataset:
            count += 1
            if record.get('parent_asin') == asin:
                found_reviews.append({
                    'Rating': record.get('rating'),
                    'Text': record.get('text'),
                    'Date Posted': "2023-Archived"
                })
            
            if len(found_reviews) >= 100: # Get more reviews for better Q&A
                break
            if count >= max_search:
                break

        if found_reviews:
            print(f"   Found {len(found_reviews)} reviews in archived dataset!")
            return pd.DataFrame(found_reviews)
        else:
            print(f"    Product not found in '{DEFAULT_DATASET_CATEGORY}' after checking {count} records.")
            return None

    except Exception as e:
        print(f"     Error streaming dataset: {e}")
        return None

#Analyze sentiment distribution and provide a simple Q&A system based on keywords in the reviews.
def analyze_sentiment(df):
    """
    Analyzes the DataFrame and prints sentiment distribution.
    """
    print("\n    Running Sentiment Analysis...")

    # Ensure numeric
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
    
    avg_rating = df['Rating'].mean()
    total_reviews = len(df)
    positive_reviews = df[df['Rating'] > 3]
    negative_reviews = df[df['Rating'] <= 3]
    
    print(f"\n    BASIC STATS:")
    print(f"      Total Reviews: {total_reviews}")
    print(f"      Average Rating: {avg_rating:.2f} / 5.0")
    print(f"      Positivity Rate: {(len(positive_reviews) / total_reviews * 100):.1f}%")

    if avg_rating >= 4.2:
        verdict = "HIGHLY RECOMMENDED"
    elif avg_rating <= 3.0:
        verdict = "NOT RECOMMENDED"
    else:
        verdict = "MIXED / AVERAGE"
    
    print(f"\n      VERDICT: {verdict}")
    print("-" * 50)

# Simple keyword-based Q&A system to explore what people say about specific aspects of the product.
def ask_questions(df):
    """
    Simple keyword-based Q&A system.
    """
    print("\n   ASK THE REVIEWS:")
    print("   Type a keyword (e.g., 'battery', 'screen', 'price') to see what people say.")
    print("   Type 'back' to choose a new product.")
    
    # Pre-process text for searching
    df['Text_Lower'] = df['Text'].astype(str).str.lower()
    
    while True:
        query = input("\n    Question/Keyword: ").strip().lower()
        
        if query in ['back', 'exit', 'quit']:
            break
            
        # Find reviews containing the keyword
        matches = df[df['Text_Lower'].str.contains(query, na=False)]
        
        if matches.empty:
            print(f"    No reviews mentioned '{query}'.")
            continue
            
        # Analyze specific sentiment for this keyword
        avg_match_rating = matches['Rating'].mean()
        sentiment = "Positive" if avg_match_rating > 3.5 else "Negative" if avg_match_rating < 2.5 else "Mixed"
        
        print(f"\n    Found {len(matches)} reviews mentioning '{query}'.")
        print(f"    Context Rating: {avg_match_rating:.1f}/5.0 ({sentiment})")
        print("-" * 30)
        
        # Show snippets (Context Window)
        print("     WHAT PEOPLE SAY:")
        for text in matches['Text'].head(3):
            # Find the sentence with the keyword for better context
            sentences = re.split(r'[.!?]', str(text))
            for s in sentences:
                if query in s.lower():
                    print(f"   - \"...{s.strip()}...\"")
                    break
        print("-" * 30)

def main():
    while True:
        print("\n" + "="*60)
        user_input = input(" Enter Amazon Link/ASIN (or 'q' to quit): ").strip()
        
        if user_input.lower() in ['q', 'quit']:
            break

        # EXTRACT ASIN
        asin_match = re.search(r'(B0[A-Z0-9]{8})', user_input)
        if asin_match:
            asin = asin_match.group(1)
            print(f"    Target ASIN: {asin}")
        else:
            print("    Invalid Link/ASIN.")
            continue

        # CHECK DATASET FIRST
        df = check_huggingface_dataset(asin)

        # FALLBACK TO SCRAPER
        if df is None:
            print("\n    Launching Live Scraper...")
            driver = Scraper.setup_driver()
            
            url = f"https://www.amazon.com/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_sr?ie=UTF8&reviewerType=all_reviews&pageNumber=1"
            driver.get(url)
            
            # --- SEPARATE CSV SAVING ---
            product_filename = f"data/{asin}_reviews.csv"
            
            # We will try to scrape 5 pages (approx 50 reviews)
            total_scraped = 0
            TARGET_PAGES = 5 
            
            from selenium.webdriver.common.by import By # Import needed for button click
            
            for page in range(1, TARGET_PAGES + 1):
                print(f"   Page {page}/{TARGET_PAGES}...")
                count = Scraper.scrape_view(driver, asin, save_filename=product_filename)
                total_scraped += count
                
                if count == 0:
                    break # Stop if no reviews found
                
                # Try clicking Next Page
                if page < TARGET_PAGES:
                    try:
                        next_button = driver.find_element(By.CSS_SELECTOR, "li.a-last a")
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(3) # Wait for load
                    except:
                        print("   Reached end of reviews.")
                        break
            
            driver.quit()
            
            if total_scraped > 0:
                try:
                    df = pd.read_csv(product_filename, on_bad_lines='skip', engine='python')
                    print(f"    Successfully loaded {len(df)} scraped reviews from '{product_filename}'.")
                except Exception as e:
                    print(f"    Error loading scraped data: {e}")
                    continue
            else:
                print("    Could not scrape reviews.")
                continue

        # ANALYZE & ASK
        if df is not None and not df.empty:
            analyze_sentiment(df)
            ask_questions(df)

if __name__ == "__main__":
    main()