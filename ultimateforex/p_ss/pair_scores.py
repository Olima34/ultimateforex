import sqlite3
import sys
import os

# DB path constants
COUNTRY_INDICATORS_DB = 'c_is/country_indicators.db'
PAIR_SCORES_DB = 'p_ss/pair_scores.db'

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PAIRS, INDICATORS, BAD_INDICATORS

# Helper for table name
def table_name(pair, indicator):
    return f"{pair}_{indicator}".replace("-", "_")

# DB connection functions
def connect_country_indicators_db():
    conn = sqlite3.connect(COUNTRY_INDICATORS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def connect_pair_scores_db():
    conn = sqlite3.connect(PAIR_SCORES_DB)
    conn.row_factory = sqlite3.Row
    return conn

# SCORING FUNCTIONS
def calculate_score(actual, consensus, forecast, indicator):
    """Calculate score for a single indicator"""
    if actual is None:
        return 0
    
    reference_value = consensus if consensus is not None else forecast
    if reference_value is None:
        return 0
    
    if actual > reference_value:
        score = 1
    elif actual < reference_value:
        score = -1
    else:
        score = 0
    
    # Invert score for bad indicators (like unemployment)
    if indicator in BAD_INDICATORS:
        score *= -1
    
    return score

def get_latest_country_indicator_data(country, indicator):
    """Get the latest data for a country-indicator from country_indicators.db"""
    try:
        with connect_country_indicators_db() as conn:
            cur = conn.execute(f'SELECT id, actual, consensus, forecast FROM "{table_name(country, indicator)}" ORDER BY id DESC LIMIT 1')
            row = cur.fetchone()
            if row:
                return {
                    'id': row['id'],
                    'actual': row['actual'],
                    'consensus': row['consensus'], 
                    'forecast': row['forecast']
                }
            return None
    except Exception as e:
        print(f"Error getting data for {country}-{indicator}: {e}")
        return None

def calculate_pair_score(pair, indicator):
    """Calculate pair score for given pair and indicator"""
    base_country, quote_country = PAIRS[pair]
    
    base_data = get_latest_country_indicator_data(base_country, indicator)
    quote_data = get_latest_country_indicator_data(quote_country, indicator)
    
    if not base_data or not quote_data:
        return None
    
    # Skip calculation if either actual value is None
    if base_data['actual'] is None or quote_data['actual'] is None:
        return None
    base_score = calculate_score(base_data['actual'], base_data['consensus'], base_data['forecast'], indicator)
    quote_score = calculate_score(quote_data['actual'], quote_data['consensus'], quote_data['forecast'], indicator)
    pair_score = base_score - quote_score
    return {
        'base_score': base_score,
        'quote_score': quote_score,
        'pair_score': pair_score,
        'base_indicator_id': base_data['id'],
        'quote_indicator_id': quote_data['id']
    }

def create_table(conn, pair, indicator):
    """Create the pair_indicator table if it does not exist"""
    with conn:
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table_name(pair, indicator)}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT,
                indicator TEXT,
                base_country TEXT,
                quote_country TEXT,
                base_score REAL,
                quote_score REAL,
                pair_score REAL,
                base_indicator_id INTEGER,
                quote_indicator_id INTEGER
            )
        ''')

def check_if_country_indicator_updated(country, indicator, last_pair_calculation_id):
    """Check if country-indicator has new data since last pair calculation"""
    try:
        with connect_country_indicators_db() as conn:
            cur = conn.execute(f'SELECT id FROM "{table_name(country, indicator)}" ORDER BY id DESC LIMIT 1')
            row = cur.fetchone()
            if row:
                latest_country_id = row['id']
                return last_pair_calculation_id < latest_country_id
            return False
    except Exception:
        return False

# MAIN LOGIC
def get_due():
    """Get due pair-indicators that need to be updated"""
    """Get due pair-indicators that need to be updated"""
    due = []
    with connect_pair_scores_db() as conn:
        for pair in PAIRS:
            base_country, quote_country = PAIRS[pair]
            for indicator in INDICATORS:
                create_table(conn, pair, indicator)
                cur = conn.execute(f'SELECT pair, indicator, base_indicator_id, quote_indicator_id FROM "{table_name(pair, indicator)}" ORDER BY id DESC LIMIT 1')
                row = cur.fetchone()
                if row:
                    base_updated = check_if_country_indicator_updated(base_country, indicator, row['base_indicator_id'])
                    quote_updated = check_if_country_indicator_updated(quote_country, indicator, row['quote_indicator_id'])
                    if base_updated or quote_updated:
                        due.append((pair, indicator, base_country, quote_country))
                else:
                    due.append((pair, indicator, base_country, quote_country))
    return due

def save_pair_score(pair, indicator, base_country, quote_country, base_score, quote_score, pair_score, base_indicator_id, quote_indicator_id):
    """Save pair score to database"""
    with connect_pair_scores_db() as conn:
        conn.execute(f'''
            INSERT INTO "{table_name(pair, indicator)}" (pair, indicator, base_country, quote_country, base_score, quote_score, pair_score, base_indicator_id, quote_indicator_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pair, indicator, base_country, quote_country, base_score, quote_score, pair_score, base_indicator_id, quote_indicator_id
        ))

def update_due():
    """Update due pair-indicators"""
    """Update due pair-indicators"""
    due = get_due()
    print("\n--- PAIR SCORES UPDATE ---")
    if not due:
        print("No pair-indicators need updating. All scores are current.")
        return 0
    updated_count = 0
    for pair, indicator, base_country, quote_country in due:
        print(f"\n[CALCULATE] {pair} - {indicator} ({base_country} vs {quote_country})")
        result = calculate_pair_score(pair, indicator)
        if result:
            save_pair_score(
                pair, indicator, base_country, quote_country,
                result['base_score'], result['quote_score'], result['pair_score'],
                result['base_indicator_id'], result['quote_indicator_id']
            )
            print(f"[OK] Saved: base_score={result['base_score']}, quote_score={result['quote_score']}, pair_score={result['pair_score']}, base_id={result['base_indicator_id']}, quote_id={result['quote_indicator_id']}")
            updated_count += 1
        else:
            print(f"[SKIP] Could not calculate score (missing data for {pair} - {indicator})")
    print(f"\nTotal updated pair-indicator combinations: {updated_count}")
    return updated_count

def run():
    """Run the update process for pair scores"""
    update_due()

if __name__ == "__main__":
    run()