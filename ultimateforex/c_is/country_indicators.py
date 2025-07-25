import requests
import pandas as pd
from io import StringIO
import sqlite3
import sys
import os

# DB path constant
COUNTRY_INDICATORS_DB = 'c_is/country_indicators.db'

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COUNTRIES, SYMBOLS, UNITS

# Helper for table name
def table_name(country, indicator):
    return f"{country}_{indicator}".replace("-", "_")

# DB connection function
def connect_country_indicators_db():
    conn = sqlite3.connect(COUNTRY_INDICATORS_DB)
    conn.row_factory = sqlite3.Row
    return conn

# FETCH FUNCTIONS
def clean(value):
    """Clean and convert string values to float"""
    if pd.isna(value) or not isinstance(value, str):
        return None
    value = value.strip()
    for s in SYMBOLS:
        value = value.replace(s, '').strip()
    if value and value[-1] in UNITS:
        try:
            return float(value[:-1]) * UNITS[value[-1]]
        except Exception:
            return None
    try:
        return float(value.replace(',', ''))
    except Exception:
        return None

def fetch(country, indicator, reference):
    """Fetch indicator data from Trading Economics"""
    try:
        url = f"https://tradingeconomics.com/{country}/{indicator}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        df = pd.read_html(StringIO(r.text))[0]
        df = df[df['Reference'] == reference]
        df['dt'] = pd.to_datetime(df['Calendar'] + ' ' + df['GMT'], format='%Y-%m-%d %I:%M %p', errors='coerce', utc=True)
        now = pd.Timestamp.now(tz='UTC')
        past = df[df['dt'] <= now]
        future = df[df['dt'] > now]
        result = {
            "country": country,
            "indicator": indicator,
            "reference": reference,
            "release_ts": int(past['dt'].iloc[-1].timestamp()) if not past.empty else None,
            "actual": clean(past['Actual'].iloc[-1]) if not past.empty else None,
            "previous": clean(past['Previous'].iloc[-1]) if not past.empty else None,
            "consensus": clean(past['Consensus'].iloc[-1]) if not past.empty else None,
            "forecast": clean(past['TEForecast'].iloc[-1]) if not past.empty else None,
            "next_update_ts": int(future['dt'].iloc[0].timestamp()) if not future.empty else None,
        }
        return result
    except Exception as e:
        print(f"Error fetching {country}-{indicator}: {e}")
        return None

# DATABASE FUNCTIONS
def create_table(conn, country, indicator):
    with conn:
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table_name(country, indicator)}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,
                indicator TEXT,
                reference TEXT,
                release_ts INTEGER,
                actual REAL,
                previous REAL,
                consensus REAL,
                forecast REAL,
                next_update_ts INTEGER
            )
        ''')

def get_due():
    """Get due country-indicators that need to be updated"""
    due = []
    with connect_country_indicators_db() as conn:
        for country in COUNTRIES:
            for indicator in COUNTRIES[country]:
                reference = COUNTRIES[country][indicator]
                create_table(conn, country, indicator)
                cur = conn.execute(f'SELECT country, indicator, reference, next_update_ts FROM "{table_name(country, indicator)}" ORDER BY id DESC LIMIT 1')
                row = cur.fetchone()
                if row:
                    next_update_ts = row['next_update_ts']
                    if not next_update_ts or next_update_ts < pd.Timestamp.now(tz='UTC').timestamp():
                        due.append((row['country'], row['indicator'], row['reference']))
                else:
                    due.append((country, indicator, reference))
    return due

def get_latest_data(country, indicator):
    with connect_country_indicators_db() as conn:
        cur = conn.execute(f'SELECT * FROM "{table_name(country, indicator)}" ORDER BY id DESC LIMIT 1')
        row = cur.fetchone()
        return dict(row) if row else None

def data_has_changed(old_data, new_data):
    """Check if the economic data has actually changed"""
    if not old_data:
        return True
    key_fields = ['release_ts', 'actual', 'previous', 'consensus', 'forecast']
    return tuple(old_data.get(f) for f in key_fields) != tuple(new_data.get(f) for f in key_fields)

def update_due():
    """Update due country-indicators and print harmonized output"""
    due = get_due()
    print("\n--- COUNTRY INDICATORS UPDATE ---")
    if not due:
        print("No country-indicators need updating. All data is current.")
        return 0
    updated_count = 0
    for country, indicator, reference in due:
        print(f"\n[FETCH] {country} - {indicator} ({reference})")
        result = fetch(country, indicator, reference)
        if result:
            latest_data = get_latest_data(country, indicator)
            with connect_country_indicators_db() as conn:
                if data_has_changed(latest_data, result):
                    conn.execute(f'''
                        INSERT INTO "{table_name(country, indicator)}" (country, indicator, reference, release_ts, actual, previous, consensus, forecast, next_update_ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        result['country'], result['indicator'], result['reference'],
                        result['release_ts'], result['actual'], result['previous'],
                        result['consensus'], result['forecast'], result['next_update_ts']
                    ))
                    print(f"[OK] Data updated: release_ts={result['release_ts']}, actual={result['actual']}, previous={result['previous']}, consensus={result['consensus']}, forecast={result['forecast']}")
                    updated_count += 1
                elif result['next_update_ts'] and result['next_update_ts'] != latest_data.get('next_update_ts'):
                    conn.execute(f'''
                        UPDATE "{table_name(country, indicator)}" 
                        SET next_update_ts = ? 
                        WHERE id = ?
                    ''', (result['next_update_ts'], latest_data['id']))
                    print(f"[SCHEDULE] Next update timestamp changed: {result['next_update_ts']}")
                else:
                    print(f"[SKIP] No changes detected. Data is already up to date.")
        else:
            print(f"[ERROR] Could not fetch data for {country} - {indicator} ({reference})")
    print(f"\nTotal updated country-indicator combinations: {updated_count}")
    return updated_count

def run():
    """Run the update process for country indicators"""
    update_due()

if __name__ == "__main__":
    run()