import os
import json
import requests
import time, random
from tqdm import tqdm
from bs4 import BeautifulSoup
# Attempt to parallelize
from concurrent.futures import ThreadPoolExecutor

def get_paths(doc):
    doc_id = doc["id"]
    year = doc["year"]
    month = doc["month"]
    
    pdf_path = os.path.join(PDF_DIR, year, month, f"{doc_id}.pdf")
    text_path = os.path.join(TEXT_DIR, year, month, f"{doc_id}.txt")
    
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    os.makedirs(os.path.dirname(text_path), exist_ok=True)
    
    return pdf_path, text_path


def download_pdf(url, path, max_retries=5):
    if os.path.exists(path):
        return True
    
    for attempt in range(max_retries):
        try:
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                
                with open(path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            f.write(chunk)
            return True
        
        except Exception as e:
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"[PDF] Retry {attempt+1} for {url} in {wait:.1f}s")
            time.sleep(wait)
    
    print("[PDF FAILED]:", url)
    return False


def download_text(url, path, max_retries=5):
    if os.path.exists(path):
        return True
    
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            
            # Force proper encoding
            r.encoding = r.apparent_encoding
            
            # Parse HTML → clean text
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Extract visible text only
            text = soup.get_text(separator="\n")
            
            # Clean extra whitespace
            lines = [line.strip() for line in text.splitlines()]
            text_clean = "\n".join(line for line in lines if line)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(text_clean)
            
            return True
        
        except Exception as e:
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"[TEXT] Retry {attempt+1} for {url} in {wait:.1f}s")
            time.sleep(wait)
    
    print("[TEXT FAILED]:", url)
    return False



def count_files(root, ext):
    total = 0
    for dirpath, _, filenames in os.walk(root):
        total += sum(1 for f in filenames if f.endswith(ext))
    return total




def process_doc(doc):
    pdf_path, text_path = get_paths(doc)
    
    results = []
    
    if not download_pdf(doc["pdf_url"], pdf_path):
        results.append({"type": "pdf", "url": doc["pdf_url"]})


    if not download_text(doc["plain_text_url"], text_path):
        results.append({"type": "text", "url": doc["plain_text_url"]})

        
    return results





if __name__ == '__main__':
    with open("output/documents.json") as f:
        docs = json.load(f)
    
    PDF_DIR = "output/pdfs"
    TEXT_DIR = "output/plain_text"

    
    failed = []
    
    # .........  This quickly checks for whether or not you've already downloaded a 
    # specific issue by checking whether or not the pdf/text filepath exists, in 
    # one very concise line.
    failed = []

    # for doc in tqdm(docs):
    #     pdf_path, text_path = get_paths(doc)
        
    #     # PDF
    #     if not download_pdf(doc["pdf_url"], pdf_path):
    #         failed.append({"type": "pdf", "url": doc["pdf_url"]})

            
    #     # TEXT
    #     if not download_text(doc["plain_text_url"], text_path):
    #         failed.append({"type": "text", "url": doc["plain_text_url"]})

    with ThreadPoolExecutor(max_workers=5) as executor:
        for result in tqdm(executor.map(process_doc, docs), total=len(docs)):
            failed.extend(result)
            
    # ......... Save failures for re-attempt
    with open("failed_downloads.json", "w") as f:
        json.dump(failed, f, indent=2)

    # ......... Check counts in docs, and counts on disk.

    print(f"Expected total docs: {len(docs)}")
    num_pdfs = count_files(PDF_DIR, ".pdf")
    num_texts = count_files(TEXT_DIR, ".txt")

    print(f"Total on disk: {num_pdfs} PDFs and {num_texts} text files.")