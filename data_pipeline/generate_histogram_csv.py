
import sqlite3
import pandas as pd

conn = sqlite3.connect("output/metadata/archive.db")

df = pd.read_sql("""
SELECT year, COUNT(*) as count
FROM documents
GROUP BY year
ORDER BY year
""", conn)

df.to_csv("output/annual_histogram_counts.csv", index=False)
