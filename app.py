from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    try:
        conn = sqlite3.connect("digitalnerds.db")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

@app.get("/")
def home():
    return {"message": "Welcome to the Phone API"}

@app.get("/phones/")
def get_all_phones():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT brand, model_name FROM phones")
    phones = cursor.fetchall()
    conn.close()
    if phones:
        return [dict(phone) for phone in phones]
    raise HTTPException(status_code=404, detail="No phones found")

@app.get("/phones/{model_name}/")
def get_phone_details(model_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    logger.debug(f"Fetching phones with search term={model_name}")

    # Preserve the original search term with spaces
    exact_term = model_name.strip()
    # Create a space-insensitive version
    space_insensitive_term = model_name.replace(" ", "")
    # Split into tokens for multi-word search
    tokens = exact_term.split()

    # Build WHERE clause dynamically for tokens
    where_conditions = " AND ".join(["LOWER(model_name) LIKE LOWER(?)"] * len(tokens))
    where_params = [f"%{token}%" for token in tokens]
    # Add space-insensitive fallback
    where_conditions += " OR LOWER(REPLACE(model_name, ' ', '')) LIKE LOWER(?)"
    where_params.append(f"%{space_insensitive_term}%")

    cursor.execute(f"""
        SELECT id, brand, model_name, model_image, specs 
        FROM phones 
        WHERE {where_conditions}
        ORDER BY 
            CASE 
                WHEN LOWER(model_name) = LOWER(?) THEN 0  -- Exact match
                WHEN LOWER(model_name) LIKE LOWER(? || '%') THEN 1  -- Starts with full term
                WHEN LOWER(model_name) LIKE LOWER('%watch ' || ? || '%') THEN 2  -- Contains "watch" + last token
                WHEN LOWER(model_name) LIKE LOWER('% ' || ? || '%') 
                     OR LOWER(model_name) LIKE LOWER(? || ' %') THEN 3  -- Standalone last token
                ELSE 4  -- Any match
            END,
            CASE 
                WHEN brand LIKE '%Samsung%' THEN 0  -- Boost Samsung
                WHEN brand LIKE '%Apple%' THEN 1    -- Boost Apple
                ELSE 2
            END,
            LENGTH(model_name),
            model_name
    """, where_params + [
        exact_term,                  # Exact match
        exact_term,                  # Starts with full term
        tokens[-1] if tokens else exact_term,  # "watch" + last token
        tokens[-1] if tokens else exact_term,  # Standalone last token (before)
        tokens[-1] if tokens else exact_term   # Standalone last token (after)
    ])

    phones = cursor.fetchall()
    conn.close()
    if phones:
        return [dict(phone) for phone in phones]
    else:
        logger.warning(f"No phones found for {model_name}")
        raise HTTPException(status_code=404, detail="Phone not found")

@app.get("/health/")
def db_health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM phones")
        count = cursor.fetchone()[0]
        conn.close()
        return {"status": "Database connected", "total_phones": count}
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)