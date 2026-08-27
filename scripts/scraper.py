import json, re, time, requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import unquote

DATA_FILE = Path(__file__).parent.parent / "data" / "campaigns.json"

QUERIES = [
    "Bhotekoshi flood relief fund 2026",
    "Rasuwa flood donation GoFundMe",
    "Nuwakot flood relief campaign",
    "Nepal flood emergency fund GlobalGiving",
    "Trishuli river flood donation 2026",
    "Dhading flood relief Nepal",
    "Bhotekoshi flash flood fundraiser",
]

PLATFORMS = {
    "gofundme.com": "GoFundMe", "globalgiving.org": "GlobalGiving",
    "justgiving.com": "JustGiving", "fundrazr.com": "FundRazr",
}

SKIP = ["facebook.com","twitter.com","x.com","youtube.com","wikipedia.org","reddit.com","instagram.com","tiktok.com","linkedin.com"]
KW = ["flood","relief","donate","fund","nepal","bhotekoshi","rasuwa","nuwakot","dhading","trishuli"]

def search_ddg(query, max_r=8):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=h, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                out.append({"title": a.get_text(strip=True), "url": unquote(m.group(1))})
        return out[:max_r]
    except Exception as e:
        print(f"  Search error: {e}"); return []

def detect_platform(url):
    u = url.lower()
    for d, p in PLATFORMS.items():
        if d in u: return p
    if any(k in u for k in ["bank","nepalrastra","pmdrf"]): return "Bank Transfer"
    if any(k in u for k in ["crypto","0x","eth","wallet"]): return "Crypto/Web3"
    return "Unknown"

def extract_info(url):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=h, timeout=15); r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        md = soup.find("meta", attrs={"name": "description"})
        desc = md.get("content", "") if md else ""
        og = soup.find("meta", property="og:title")
        title = og.get("content", "") if og else ""
        ogd = soup.find("meta", property="og:description")
        if ogd: desc = ogd.get("content", "") or desc
        return {"title": title, "description": desc}
    except: return {}

def trigrams(s):
    s = s.lower(); return set(s[i:i+3] for i in range(len(s)-2))

def score(c, all_c):
    s = 50
    try:
        h = (datetime.now(timezone.utc) - datetime.fromisoformat(c["created_date"].replace("Z","+00:00"))).total_seconds()/3600
        if h < 72: s -= 30
    except: pass
    reg = (c.get("registration_id") or "").lower()
    if reg.startswith("swc"): s += 40
    elif reg.startswith("gov"): s += 45
    story = c.get("story","")
    if story:
        for o in all_c:
            if o.get("id")==c.get("id"): continue
            os = o.get("story","")
            if os:
                t1, t2 = trigrams(story), trigrams(os)
                if t1|t2 and len(t1&t2)/len(t1|t2) > 0.75: s -= 40; break
    if c.get("organizer_type")=="Anonymous": s -= 20
    if c.get("wallet_address"): s -= 15
    p = c.get("platform","")
    if p=="GlobalGiving": s += 5
    elif p=="Crypto/Web3": s -= 10
    s = max(0, min(100, s))
    st = "verified" if s >= 80 else ("flagged" if s < 35 else "community")
    return s, st

def main():
    print("=== Bhotekoshi Flood Relief Scraper ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    existing = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else []
    print(f"Loaded {len(existing)} existing campaigns")
    results, seen = [], set()
    for q in QUERIES:
        print(f"Searching: {q}")
        for r in search_ddg(q):
            if r["url"] not in seen: seen.add(r["url"]); results.append(r)
        time.sleep(2)
    print(f"Found {len(results)} search results")
    new = []
    for r in results:
        url, text = r["url"], (r('title')+" "+r["url"]).lower()
        if not any(k in text for k in KW): continue
        if any(d in url for d in SKIP): continue
        if any(c.get("url","").rstrip("/")==url.rstrip("/") for c in existing+new): continue
        plat = detect_platform(url)
        if plat=="Unknown" and not any(k in text for k in ["fund","donate","relief","campaign"]): continue
        # print(f"  New: {r('title')[:60]}... [{plat}]")
        print(f"  New: {r['title'][:60]}... [{plat}]")
        info = extract_info(url); time.sleep(1)
        new.append({"id":f"AUTO-{len(existing)+len(new)+1:03d}","title":info.get("title") or r('title'),"platform":plat,"organizer":"Unknown (auto-discovered)","organizer_type":"Unverified","location":"Auto-discovered","registration_id":None,"url":url,"funds_raised_usd":0,"target_usd":0,"created_date":datetime.now(timezone.utc).isoformat(),"story":info.get("description") or r('title'),"wallet_address":None,"auto_discovered":True})
    print(f"New campaigns: {len(new)}")
    if not new: print("No new campaigns found."); return
    all_c = existing + new
    for c in all_c:
        s, st = score(c, all_c); c["trustScore"]=s; c["trustStatus"]=st
    all_c.sort(key=lambda c: (0 if c["trustStatus"]=="verified" else 1 if c["trustStatus"]=="community" else 2, -c["trustScore"]))
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(all_c, indent=2, ensure_ascii=False))
    print(f"Saved {len(all_c)} campaigns ({len(new)} new)")

if __name__ == "__main__": main()
