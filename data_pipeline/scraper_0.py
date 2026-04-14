import os  # you're using it but didn't import it yet
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import tqdm
import time
import random
import json


def get_pagination_links(html):
    soup = BeautifulSoup(html, "html.parser")
    
    links = []
    
    for a in soup.select('a[href*="startDoc="]'):
        href = a.get("href")
        full_url = urljoin(BASE, href)
        links.append(full_url)
    
    return list(set(links))  # remove duplicates



def get_doc_links_from_page(url):
    html = fetch_with_retries(url)
    
    if html is None:
        return None, None  # signal failure
    
    soup = BeautifulSoup(html, "html.parser")
    
    links = []
    for doc in soup.select("div.row.docHit"):
        a_tag = doc.find("a")
        if a_tag:
            full_url = urljoin(BASE, a_tag["href"])
            links.append(full_url)


    return links, html


# Exponential backoff
def fetch_with_retries(url, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        
        except Exception as e:
            wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"Retry {attempt+1} for {url} in {wait:.2f}s")
            time.sleep(wait)
    
    return None  # failed after retries


def save_progress(all_links, failed_pages):
    os.makedirs("output", exist_ok=True)
    
    with open("output/links.json", "w") as f:
        json.dump(list(set(all_links)), f)
    
    with open("output/failed_pages.json", "w") as f:
        json.dump(failed_pages, f)



if __name__ == '__main__':
    # calls time.sleep(0.5) between requests
    BE_POLITE = True

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; ArchiveBot/1.0)"
    }
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # *************************************************************** SETUP
    # --------- Retrieve iFrame URL --------- 
    url = "https://chicagomaroon.com/archive/"
    html = session.get(url).text
    
    soup = BeautifulSoup(html, "html.parser")
    
    iframe = soup.find("iframe")
    iframe_src = iframe["src"]
    
    print(iframe_src)
    
    
    # --------- Send request to iFrame URL --------- 
    BASE = "https://campub.lib.uchicago.edu"
    
    iframe_url = iframe_src if iframe_src.startswith("http") else BASE + iframe_src
    
    html = requests.get(iframe_url).text
    soup = BeautifulSoup(html, "html.parser")

    
    
    # --------- Extract links on landing page ---------
    # (page 1 is not a url!!! must be treated differently)
    # This needs to happen before pagination bc soup will change 
    # (ordering is weird but necessary)
    
    all_links = []
    
    for doc in soup.select("div.row.docHit"):
        a_tag = doc.find("a")
        if a_tag:
            full_url = urljoin(BASE, a_tag["href"])
            all_links.append(full_url)



    # --------- Compile urls of all pages for pagination ---------
    html = requests.get("https://campub.lib.uchicago.edu/search/?f1-title=Daily+Maroon").text
    pages = get_pagination_links(html)

    pages = sorted(
        pages,
        key=lambda p: int(p[p.rfind('=')+1:])
    )
    
    pages = pages[1:] # Ignore first link (page 1 has no ref, will cause problems later)
    
    print(len(pages), 'pages. Page urls retrieved.')

    # *************************************************************** CRAWLER
    # --------- Try all links, create queue with failed pages ---------
    failed_pages = []

    try: 
        for i, page_url in enumerate(tqdm.tqdm(pages)):
            links, html = get_doc_links_from_page(page_url)
            
            if links is None:
                failed_pages.append(page_url)
                continue
            
            if not links:
                print(f"Empty page (likely failure): {page_url}")
                failed_pages.append(page_url)
                print("HTML preview:", html[:500])
                continue
            
            all_links.extend(links)
            all_links = list(set(all_links))
        
            if i % 10 == 0:
                save_progress(all_links, failed_pages)
            
            if BE_POLITE:
                time.sleep(random.uniform(0.3, 1.0))

    except KeyboardInterrupt:
        print("Interrupted! Saving progress...")
        save_progress(all_links, failed_pages)

    
    # (Below is un-tested bc the above code has just worked!)
    # --------- Retry failed pages until done ---------
    
    round_num = 1
    while (failed_pages) and (round_num <=  1_000):
        print(f"\nRetry round {round_num}, {len(failed_pages)} pages left")
        
        new_failed = []
        
        for page_url in tqdm.tqdm(failed_pages):
            links, html = get_doc_links_from_page(page_url)
            
            if links is None:
                new_failed.append(page_url)
                continue
            
            all_links.extend(links)
        
        failed_pages = new_failed
        round_num += 1
