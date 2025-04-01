       
import sqlite3
import pandas as pd
from datetime import datetime
       

def db_to_csv(db_path):
        
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        for table in tables:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            if not df.empty:
                df.to_csv(f"{table}.csv", index=False)
                print(f"Exported {table} to {table}.csv")
            else:
                print(f"skipped {table}, it was empty")

                      
db_to_csv("slim_gh_grabber/fixed_issues.db")