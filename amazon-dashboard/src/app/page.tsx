'use client';

import { useState } from 'react';

export default function Dashboard() {
  const [asin, setAsin] = useState("");
  const [loading, setLoading] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [keywordResult, setKeywordResult] = useState<any | null>(null);
  const [keywordLoading, setKeywordLoading] = useState(false);
  const [keywordError, setKeywordError] = useState("");

  const runAnalysis = async () => {
    if (!asin) return;
    setLoading(true);
    setError("");

    try {
      // Calls your Python FastAPI Server!
      const response = await fetch("http://127.0.0.1:8000/api/analyze-absa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asin: asin.trim() })
      });

      if (!response.ok) throw new Error("Failed to fetch data. Is the ASIN correct?");

      const data = await response.json();
      setReportData(data);

    } catch (err: any) {
      setError(err.message);
    }
    setLoading(false);
  };

  const searchKeyword = async () => {
    if (!keyword.trim()) return;
    setKeywordLoading(true);
    setKeywordResult(null);
    setKeywordError("");

    try {
      const response = await fetch("http://127.0.0.1:8000/api/ask-reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asin: asin.trim(), keyword: keyword.trim() })
      });

      if (!response.ok) throw new Error("Failed to search reviews.");

      const data = await response.json();
      setKeywordResult(data);
    } catch (err: any) {
      setKeywordError(err.message);
    }
    setKeywordLoading(false);
  };

  const sentimentColor = (label: string) => {
    if (!label) return "text-muted-foreground";
    const l = label.toLowerCase();
    if (l.includes("positive")) return "text-green-600";
    if (l.includes("negative")) return "text-red-600";
    return "text-yellow-600";
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] p-8 font-sans flex flex-col items-center">

      {/* HEADER & SEARCH BAR */}
      <div className="w-full max-w-4xl text-center mb-12 mt-10">
        <h1 className="text-4xl font-bold text-primary mb-2">Amazon Review Analyzer</h1>
        <p className="text-muted-foreground mb-8">Instant ABSA Insights from millions of reviews.</p>

        <div className="flex justify-center gap-3">
          <input
            type="text"
            placeholder="Enter Amazon ASIN or URL"
            className="px-5 py-3 border border-border bg-input-background rounded-lg w-96 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
            value={asin}
            onChange={(e) => setAsin(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runAnalysis()}
          />
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? "Analyzing..." : "Analyze"}
          </button>
        </div>
        {error && <p className="text-destructive mt-4">{error}</p>}
      </div>

      {/* DASHBOARD RESULTS */}
      {reportData && (
        <div className="w-full max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-500">

          {/* Metrics Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
             <div className="bg-card p-6 rounded-lg shadow-sm border border-border">
               <h3 className="text-muted-foreground text-sm font-medium mb-1">Total Reviews Analyzed</h3>
               <p className="text-3xl font-bold text-primary">{reportData.total_analyzed}</p>
             </div>
             <div className="bg-card p-6 rounded-lg shadow-sm border border-border">
               <h3 className="text-muted-foreground text-sm font-medium mb-1">Data Source</h3>
               <p className="text-xl font-bold text-primary mt-2">Hybrid Engine ✅</p>
             </div>
             <div className="bg-card p-6 rounded-lg shadow-sm border border-border">
               <h3 className="text-muted-foreground text-sm font-medium mb-1">Status</h3>
               <div className="mt-2 inline-block px-3 py-1 bg-green-100 text-green-800 font-semibold rounded-full text-sm">
                 Successfully Parsed
               </div>
             </div>
          </div>

          {/* Final Verdict */}
          {reportData.final_verdict && (() => {
            const v = reportData.final_verdict;
            const isGood = v.label === "Recommended";
            const isBad = v.label === "Not Recommended";
            const barColor = isGood ? 'bg-green-500' : isBad ? 'bg-destructive' : 'bg-yellow-400';
            const badgeBg = isGood ? 'bg-green-100 text-green-800' : isBad ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800';
            return (
              <div className="bg-card p-8 rounded-lg shadow-sm border border-border mb-8">
                <h2 className="text-2xl font-bold mb-6 text-primary border-b border-border pb-4">Final Verdict</h2>
                <div className="flex items-center gap-6">
                  <span className={`px-4 py-2 rounded-full font-bold text-lg ${badgeBg}`}>{v.label}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${(v.score / 5) * 100}%` }}></div>
                      </div>
                      <span className="font-bold text-xl text-primary whitespace-nowrap">{v.score.toFixed(1)}/5.0</span>
                    </div>
                    <p className="text-muted-foreground text-sm">{v.detail}</p>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ABSA Results Map */}
          <div className="bg-card p-8 rounded-lg shadow-sm border border-border">
            <h2 className="text-2xl font-bold mb-6 text-primary border-b border-border pb-4">Aspect-Based Sentiment</h2>

            <div className="space-y-6">
              {Object.entries(reportData.absa_report).map(([aspect, data]: [string, any]) => (
                 <div key={aspect} className="flex justify-between items-center group">
                    <span className="font-semibold text-lg capitalize text-foreground w-1/4">{aspect}</span>

                    {/* Visual Progress Bar */}
                    <div className="w-1/2 h-3 bg-muted rounded-full overflow-hidden mx-4">
                      <div
                        className={`h-full rounded-full ${data.score >= 4 ? 'bg-green-500' : data.score >= 3 ? 'bg-yellow-400' : 'bg-destructive'}`}
                        style={{ width: `${(data.score / 5) * 100}%` }}
                      ></div>
                    </div>

                    <div className="w-1/4 text-right flex items-center justify-end gap-3">
                      <span className="font-bold text-xl text-primary">{data.score.toFixed(1)}/5.0</span>
                      <span className="bg-muted px-3 py-1 rounded-full text-sm font-medium text-foreground w-24 text-center">
                        {data.label}
                      </span>
                    </div>
                 </div>
              ))}
            </div>
          </div>

          {/* Ask the Reviews */}
          <div className="bg-card p-8 rounded-lg shadow-sm border border-border mt-8">
            <h2 className="text-2xl font-bold mb-6 text-primary border-b border-border pb-4">Ask the Reviews</h2>

            <div className="flex gap-3 mb-4">
              <input
                type="text"
                placeholder="Search keyword (e.g. battery, screen, price...)"
                className="px-5 py-3 border border-border bg-input-background rounded-lg flex-1 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && searchKeyword()}
              />
              <button
                onClick={searchKeyword}
                disabled={keywordLoading}
                className="px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {keywordLoading ? "Searching..." : "Search"}
              </button>
            </div>

            {keywordError && <p className="text-destructive mb-4">{keywordError}</p>}

            {keywordResult && (
              <div className="bg-muted rounded-lg p-6 border border-border">
                <p className="text-foreground mb-2">
                  <span className="font-bold">{keywordResult.count}</span> reviews mention &quot;<span className="font-bold">{keywordResult.keyword}</span>&quot;
                </p>

                {keywordResult.count > 0 ? (
                  <>
                    <p className="mb-4">
                      <span className="text-foreground font-medium">Avg rating: {keywordResult.avg_rating?.toFixed(1)}</span>
                      {" — "}
                      <span className={`font-semibold ${sentimentColor(keywordResult.sentiment)}`}>
                        {keywordResult.sentiment}
                      </span>
                    </p>

                    <div className="space-y-3">
                      {(keywordResult.sample_reviews ?? []).slice(0, 5).map((review: string, i: number) => (
                        <blockquote key={i} className="border-l-4 border-border pl-4 text-muted-foreground text-sm italic">
                          {review.length > 200 ? review.slice(0, 200) + "…" : review}
                        </blockquote>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="text-muted-foreground text-sm">No reviews mentioned this keyword.</p>
                )}
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
