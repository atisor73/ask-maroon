from urllib.parse import urlparse, parse_qs
import json
import tqdm

def extract_doc_id(url):
    query = urlparse(url).query
    params = parse_qs(query)
    return params.get("docId", [None])[0]

def parse_date_from_doc_id(doc_id):
    try:
        parts = doc_id.split("-")
        year = parts[2]
        md = parts[3].zfill(4)  # ensure 4 digits
        
        month = md[:2]
        day = md[2:]
        date = f"{year}-{month}-{day}"
        
        return date, year, month, day
    except Exception:
        return None, None, None, None

def build_doc_record(doc_url):
    doc_id = extract_doc_id(doc_url)
    
    if not doc_id:
        return None
    
    date, year, month, day = parse_date_from_doc_id(doc_id)
    
    pdf_url  = f"https://campub.lib.uchicago.edu/pdf/?docId={doc_id}"
    text_url = f"https://campub.lib.uchicago.edu/text/?docId={doc_id}"
    
    return {
        "id": doc_id,
        "date": date,  
        "year": year,
        "month": month,
        "day":day,
        "doc_url": doc_url,
        "pdf_url": pdf_url,
        "plain_text_url": text_url
    }


if __name__ == '__main__':
    with open("output/links.json") as f:
        doc_links = json.load(f)
    
    docs = []
    
    for doc_url in tqdm.tqdm(doc_links):
        record = build_doc_record(doc_url)
        if record:
            docs.append(record)
    
    with open("output/documents.json", "w") as f:
        json.dump(docs, f, indent=2)

        