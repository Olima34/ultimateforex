import sqlite3
import json
import os
import sys

# DB path constants
PAIR_SCORES_DB = 'p_ss/pair_scores.db'
TOTAL_SCORE_DB = 'p_t_s/pair_total_score.db'

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PAIRS, INDICATORS

# Helper for table name
def total_score_table_name(pair):
    return f"{pair}_total_score"

def indicator_table_name(pair, indicator):
    return f"{pair}_{indicator}".replace("-", "_")

# DB connection functions
def connect_total_score_db():
    conn = sqlite3.connect(TOTAL_SCORE_DB)
    conn.row_factory = sqlite3.Row
    return conn

def connect_pair_scores_db():
    conn = sqlite3.connect(PAIR_SCORES_DB)
    conn.row_factory = sqlite3.Row
    return conn

# Table creation
def create_total_score_table(conn, pair):
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS "{total_score_table_name(pair)}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT,
            total_score REAL,
            indicator_scores TEXT,
            indicator_row_ids TEXT
        )
    ''')

# Get latest indicator scores and row ids for a pair
def get_latest_indicator_scores(pair):
    scores = {}
    row_ids = {}
    with connect_pair_scores_db() as conn:
        for indicator in INDICATORS:
            table = indicator_table_name(pair, indicator)
            cur = conn.execute(f'SELECT id, pair_score FROM "{table}" ORDER BY id DESC LIMIT 1')
            row = cur.fetchone()
            if row:
                scores[indicator] = row['pair_score']
                row_ids[indicator] = row['id']
            else:
                scores[indicator] = None
                row_ids[indicator] = None
    return scores, row_ids

# Get latest total score row for a pair
def get_latest_total_score_row(conn, pair):
    cur = conn.execute(f'SELECT * FROM "{total_score_table_name(pair)}" ORDER BY id DESC LIMIT 1')
    row = cur.fetchone()
    return row

# Check if update is needed
def should_update(latest_row_ids, saved_row_ids):
    if not saved_row_ids:
        return True
    for indicator in INDICATORS:
        if latest_row_ids.get(indicator) is None:
            continue
        if saved_row_ids.get(indicator) is None or latest_row_ids[indicator] > saved_row_ids[indicator]:
            return True
    return False

# Save total score
def save_total_score(conn, pair, total_score, indicator_scores, indicator_row_ids):
    conn.execute(f'''
        INSERT INTO "{total_score_table_name(pair)}" (pair, total_score, indicator_scores, indicator_row_ids)
        VALUES (?, ?, ?, ?)
    ''', (
        pair,
        total_score,
        json.dumps(indicator_scores),
        json.dumps(indicator_row_ids)
    ))

# Main update logic

# Get due pairs that need to be updated
def get_due():
    """Get due pairs that need to be updated"""
    due = []
    with connect_total_score_db() as conn:
        for pair in PAIRS:
            create_total_score_table(conn, pair)
            indicator_scores, indicator_row_ids = get_latest_indicator_scores(pair)
            latest_row = get_latest_total_score_row(conn, pair)
            saved_row_ids = None
            if latest_row:
                try:
                    saved_row_ids = json.loads(latest_row['indicator_row_ids'])
                except Exception:
                    saved_row_ids = None
            if should_update(indicator_row_ids, saved_row_ids):
                due.append((pair, indicator_scores, indicator_row_ids))
    return due

# Update due pairs
def update_due():
    """Update due pairs"""
    due = get_due()
    print("\n--- PAIR TOTAL SCORE UPDATE ---")
    if not due:
        print("No pair total scores need updating. All scores are current.")
        return 0
    updated_count = 0
    with connect_total_score_db() as conn:
        for pair, indicator_scores, indicator_row_ids in due:
            total_score = sum([score for score in indicator_scores.values() if score is not None])
            save_total_score(conn, pair, total_score, indicator_scores, indicator_row_ids)
            print(f"[OK] Updated: {pair} total_score={total_score}, indicator_scores={indicator_scores}, indicator_row_ids={indicator_row_ids}")
            updated_count += 1
    print(f"\nTotal updated pairs: {updated_count}")
    return updated_count

def run():
    """Run the update process for pair total scores"""
    update_due()

if __name__ == "__main__":
    run()