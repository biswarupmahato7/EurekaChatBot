import requests
from bs4 import BeautifulSoup
import time

headers = {"User-Agent": "EurekaRAGBot/1.0 (Phase A Inspection; read-only)"}
session = requests.Session()

test_urls = [
    "https://eurekasolutions.in/about-us",
    "https://eurekasolutions.in/services",
    "https://eurekasolutions.in/contact-us",
    "https://eurekasolutions.in/services/ai-intelligent-automation",
    "https://eurekasolutions.in/Eureka2026/",
]

for url in test_urls:
    r = session.get(url, headers=headers, timeout=15, allow_redirects=True)
    soup = BeautifulSoup(r.text, "lxml")
    title = soup.find("title")
    t = title.text if title else "NONE"
    body = soup.get_text(separator=" ", strip=True)
    main = soup.find("main")
    links = [a.get("href", "") for a in soup.find_all("a", href=True)]
    internal = [lk for lk in links if lk.startswith("/") and not lk.startswith("//")]
    canonical = soup.find("link", rel="canonical")
    canon_href = canonical.get("href", "NONE") if canonical else "NONE"
    scripts = soup.find_all("script", src=True)
    print(f"[{r.status_code}] {url}")
    print(f"  final_url: {r.url}")
    print(f"  Title: {t}")
    print(f"  Canonical: {canon_href}")
    print(f"  Body length: {len(body)}")
    print(f"  Preview: {repr(body[:200])}")
    print(f"  Has main: {main is not None}")
    print(f"  Internal links: {len(internal)}")
    print(f"  External scripts: {len(scripts)}")
    print()
    time.sleep(1)
