import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
import re
import csv
from datetime import datetime

def setup_driver():
    """Starts the browser once and keeps it open."""
    print("Launching Browser...")
    options = uc.ChromeOptions()
    profile_path = os.path.join(os.getcwd(), "chrome_profile")
    options.add_argument(f"--user-data-dir={profile_path}")
    
    # --- FIX: Removed 'version_main=143' so it auto-detects your version 145 ---
    driver = uc.Chrome(options=options) 
    return driver

def scrape_view(driver, asin, save_filename="training_data.csv"):
    """Captures currently visible reviews and saves to a specific file."""
    print(f"   Capturing reviews on screen to '{save_filename}'...")
    
    try:
        # Fast wait - user already said they are ready
        wait = WebDriverWait(driver, 5) 
        
        # 1. FIND REVIEWS
        # Star Validation
        star_selectors = ["i[data-hook='review-star-rating']", "i.review-rating", "span.a-icon-alt"]
        found_stars = False
        for selector in star_selectors:
            try:
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                found_stars = True
                break
            except:
                continue
        
        if not found_stars:
            print("   No reviews detected. Make sure you are on a review page!")
            return 0

        # Data Extraction
        review_bodies = driver.find_elements(By.CSS_SELECTOR, "span[data-hook='review-body']")
        all_stars = driver.find_elements(By.CSS_SELECTOR, "i[data-hook='review-star-rating']")
        
        if not review_bodies:
             # Backup selector
             review_bodies = driver.find_elements(By.XPATH, "//span[contains(@class, 'review-text')]")

        # 2. SAVE TO SPECIFIC CSV
        # Ensure directory exists if path is provided
        if "/" in save_filename or "\\" in save_filename:
            os.makedirs(os.path.dirname(save_filename), exist_ok=True)
            
        file_exists = os.path.isfile(save_filename)
        saved_count = 0
        
        with open(save_filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Only write header if file is new
            if not file_exists:
                writer.writerow(["Rating", "Text", "Date Posted"])
            
            for index, body_elem in enumerate(review_bodies):
                try:
                    text = body_elem.text.strip().replace("\n", " ")
                    
                    # Rating matching logic
                    try:
                        rating_str = all_stars[index].get_attribute("textContent")
                        rating = rating_str.split(" ")[0]
                    except:
                        rating = "3.0" # Default neutral

                    if len(text) > 0:
                        # Write row with Date
                        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        writer.writerow([rating, text, current_time])
                        saved_count += 1
                except:
                    pass
                    
        return saved_count

    except Exception as e:
        print(f"   Error capturing: {e}")
        return 0

def run_scraper():
    driver = setup_driver()
    
    try:
        # --- OUTER LOOP: SELECT PRODUCT ---
        while True:
            print("\n" + "="*60)
            print(" MODES:")
            print("   1. Single Page: Enter 'ASIN' (e.g., B08T5QVTKW)")
            print("   2. Multi-Page:  Enter 'ASIN PAGES' (e.g., B08T5QVTKW 5)")
            print("   3. Exit:        Type 'quit'")
            
            user_input = input("\n> ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                break

            # Parse Input (ASIN + Optional Page Count)
            parts = user_input.split()
            target_asin = parts[0]
            target_pages = 1
            
            if len(parts) > 1 and parts[1].isdigit():
                target_pages = int(parts[1])

            # Extract ASIN using Regex
            asin_match = re.search(r'(B0[A-Z0-9]{8})', target_asin)
            if asin_match:
                current_asin = asin_match.group(1)
            else:
                print("Invalid ASIN. Try again.")
                continue

            # Navigate to Page 1
            url = f"https://www.amazon.com/product-reviews/{current_asin}/ref=cm_cr_arp_d_viewopt_sr?ie=UTF8&reviewerType=all_reviews&pageNumber=1"
            print(f"Navigating to {current_asin}...")
            driver.get(url)
            
            # --- PAGINATION LOOP ---
            total_captured = 0
            for page in range(1, target_pages + 1):
                print(f"\n   Processing Page {page} of {target_pages}...")
                
                # Scrape Current Page
                count = scrape_view(driver, current_asin)
                total_captured += count
                
                if count == 0:
                    print("   No reviews found on this page. Stopping.")
                    break
                
                # Click Next Page (if more pages requested)
                if page < target_pages:
                    try:
                        next_button = driver.find_element(By.CSS_SELECTOR, "li.a-last a")
                        driver.execute_script("arguments[0].click();", next_button)
                        print("   ➡️  Clicking 'Next Page'...")
                        time.sleep(3) # Wait for load
                    except:
                        print("   No 'Next Page' button found. End of reviews.")
                        break
            
            print(f"\nFinished! Scraped {total_captured} reviews for {current_asin}.")

    except KeyboardInterrupt:
        print("\nSee ya!")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper()