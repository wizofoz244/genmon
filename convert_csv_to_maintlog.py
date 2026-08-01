#!/usr/bin/env python3
"""
Convert CSV status history / service logs into Genmon's maintlog.json format.
Usage:
    python3 convert_csv_to_maintlog.py [path_to_csv] [path_to_output_json]
"""

import sys
import os
import csv
import json
from datetime import datetime

def parse_date(date_str):
    date_str = str(date_str).strip()
    formats = [
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%m/%d/%Y %H:%M")
        except ValueError:
            pass
    # Default fallback
    return date_str

def parse_type(type_str):
    type_str = str(type_str).strip().title()
    allowed = ["Maintenance", "Check", "Repair", "Observation"]
    for a in allowed:
        if a.lower() in type_str.lower():
            return a
    return "Observation"

def parse_hours(hours_val):
    try:
        return float(hours_val)
    except (ValueError, TypeError):
        return 0.0

def convert_csv_to_json(csv_path, output_json_path):
    if not os.path.isfile(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return False

    entries = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        
        # Find column mappings
        date_col = next((h for h in reader.fieldnames if any(k in h.lower() for k in ['date', 'time', 'timestamp'])), None)
        type_col = next((h for h in reader.fieldnames if any(k in h.lower() for k in ['type', 'category', 'event', 'status'])), None)
        hours_col = next((h for h in reader.fieldnames if any(k in h.lower() for k in ['hour', 'hrs', 'engine_hours', 'run_hours'])), None)
        comment_col = next((h for h in reader.fieldnames if any(k in h.lower() for k in ['comment', 'desc', 'description', 'message', 'note', 'details'])), None)

        for row in reader:
            date_val = row.get(date_col, "") if date_col else ""
            type_val = row.get(type_col, "Maintenance") if type_col else "Maintenance"
            hours_val = row.get(hours_col, 0) if hours_col else 0
            comment_val = row.get(comment_col, "") if comment_col else ""

            if not date_val and not comment_val:
                continue

            entry = {
                "date": parse_date(date_val),
                "type": parse_type(type_val),
                "hours": parse_hours(hours_val),
                "comment": str(comment_val).strip()
            }
            entries.append(entry)

    with open(output_json_path, 'w', encoding='utf-8') as outfile:
        json.dump(entries, outfile, indent=4)

    print(f"Successfully converted {len(entries)} entries to {output_json_path}")
    return True

if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "statusHistory.csv"
    json_file = sys.argv[2] if len(sys.argv) > 2 else "maintlog.json"
    convert_csv_to_json(csv_file, json_file)
