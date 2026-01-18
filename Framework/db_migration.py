import sqlite3
import csv
import os

def export_sqlite_to_csv():
    """Export all tables from SQLite database to CSV files"""
    # Connect to SQLite database
    conn = sqlite3.connect('translucent_bot.db')
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # Create export directory
    os.makedirs('db_export', exist_ok=True)
    
    # Export each table to CSV
    for table in tables:
        table_name = table[0]
        print(f"Exporting table: {table_name}")
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Export data
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Write to CSV
        with open(f"db_export/{table_name}.csv", 'w', newline='') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(columns)
            csv_writer.writerows(rows)
        
        print(f"Exported {len(rows)} rows from {table_name}")
    
    conn.close()
    print("Export complete!")

if __name__ == "__main__":
    export_sqlite_to_csv() 