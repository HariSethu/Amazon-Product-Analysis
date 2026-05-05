from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import re
import Hybrid_Analysis as ha
import Scraper
from fastapi.middleware.cors import CORSMiddleware

#init FastAPI app
app = FastAPI(
    title = "Amazon Review Analyzer API",
    description = "An API to scrape, fetch, and analyze Amazon reviews for a given ASIN using ABSA.",
    version = "1.0.0")


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

def extract_asin(raw_input: str) -> str:
    match = re.search(r'(B0[A-Z0-9]{8})', raw_input.upper())
    if match:
        return match.group(1)
    raise HTTPException(
        status_code=422,
        detail="Invalid ASIN or Amazon URL. Please provide a valid 10-character ASIN (e.g. B08XVYZ1Y5) or an Amazon product URL."
    )

#Define Request Models
class ProductRequest(BaseModel):
    asin: str

class ScrapeRequest(BaseModel):
    asin: str
    pages: int = 5 #default to 5 pages of reviews if not specified

class KeywordRequest(BaseModel):
    asin: str
    keyword: str

#API Endpoints

@app.get("/")
def read_root():
    """ Confirm API is running. """
    return{"status": "online", "message": "Welcome to the Amazon Review Analyzer API!"}

@app.post("/api/fetch_reviews")
def fetch_huggingface_reviews(request: ProductRequest):
    """
    Attempt to pull review data from 2023 Hugging Face dataset exclusively
    """

    asin = extract_asin(request.asin)
    df = ha.gather_data_concurrently(asin)

    if df is not None and not df.empty:
        reviews_list = df[['Rating', 'Text', 'Date Posted']].head(50).to_dict(orient='records')
        return{
            "asin": asin,
            "source": "Hugging Face Datasets",
            "total_reviews": len(df),
            "reviews": reviews_list
        }
    raise HTTPException(status_code=404, detail=f"No reviews found for ASIN {asin} in Hugging Face datasets.")

@app.post("/api/scrape_reviews")
def scrape_live_reviews(request: ScrapeRequest):
    """
    Force a live scrape using undetected chrome driver
    """
    asin = extract_asin(request.asin)
    #Call the scraper directly
    df = ha.run_scraper_thread(asin)

    if df is not None and not df.empty:
        reviews_list = df[['Rating', 'Text', 'Date Posted']].head(50).to_dict(orient='records')
        return{
            "asin": asin,
            "source": "Live Scrape",
            "total_reviews": len(df),
            "reviews": reviews_list
        }
    raise HTTPException(status_code = 500, detail = f"Live scraping failed for ASIN {asin}. Bot Detection? Try again later or check logs for details.")

@app.post("/api/analyze-absa") # 1. Changed to match React's fetch URL exactly
def run_absa_analysis(request: ProductRequest):
    """
    Run ABSA analysis on the reviews for a given ASIN. This will attempt to fetch reviews first, then analyze them.
    """
    asin = extract_asin(request.asin)
    df = ha.gather_data_concurrently(asin)

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No data found to analyze.")
    
    # Run Analysis
    try:
        aspect_sentiment = ha.analyze_aspects(df)

        # Compute weighted-average verdict across all aspects (weight = mention count)
        final_verdict = None
        if aspect_sentiment:
            total_weight = sum(d['mentions'] for d in aspect_sentiment.values())
            weighted_sum = sum(d['score'] * d['mentions'] for d in aspect_sentiment.values())
            avg = weighted_sum / total_weight if total_weight else 0

            if avg >= 4.0:
                label, detail = "Recommended", "Customers are largely satisfied with this product."
            elif avg >= 3.0:
                label, detail = "Mixed Reviews", "Customers have mixed opinions — check the aspects below."
            else:
                label, detail = "Not Recommended", "Customers are largely dissatisfied with this product."

            final_verdict = {"score": round(avg, 1), "label": label, "detail": detail}

        return{
            "asin": asin,
            "total_analyzed": len(df),
            "final_verdict": final_verdict,
            "absa_report": aspect_sentiment
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ask-reviews")
def ask_reviews(request: KeywordRequest):
    """
    Filter reviews by keyword and return sentiment summary.
    """
    asin = extract_asin(request.asin)
    keyword = request.keyword.strip().lower()

    df = ha.gather_data_concurrently(asin)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No data found for this product.")

    df = df.drop_duplicates(subset=['Text'])
    matches = df[df['Text'].astype(str).str.lower().str.contains(keyword, na=False)]

    if matches.empty:
        return {
            "asin": asin,
            "keyword": keyword,
            "count": 0,
            "avg_rating": None,
            "sentiment": "No mentions found",
            "sample_reviews": []
        }

    avg_rating = round(matches['Rating'].mean(), 1)
    sentiment = "Positive" if avg_rating > 3.5 else "Negative" if avg_rating < 2.5 else "Mixed"

    return {
        "asin": asin,
        "keyword": keyword,
        "count": len(matches),
        "avg_rating": avg_rating,
        "sentiment": sentiment,
        "sample_reviews": matches['Text'].head(5).tolist()
    }