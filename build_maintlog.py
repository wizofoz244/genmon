import os
import csv
import json
from datetime import datetime

csv_path = os.path.expanduser('~/Google Drive/My Drive/Scans/statusHistory.csv')
output_json = '/Users/oz/Develop/genmon/maintlog.json'

service_keywords = ['battery', 'service', 'reset', 'maintenance', 'inspect', 'repair']

raw_events = []
with open(csv_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
    reader = csv.DictReader(f)
    reader.fieldnames = [h.strip() for h in reader.fieldnames]
    for r in reader:
        desc = r.get('Description', '').strip()
        dt_str = r.get('Date Time', '').strip()
        if any(k in desc.lower() for k in service_keywords):
            raw_dt = dt_str.split(' America')[0].strip()
            try:
                dt_obj = datetime.strptime(raw_dt, '%m/%d/%Y %I:%M:%S %p')
            except Exception as e:
                continue
            raw_events.append((dt_obj, desc))

# Sort chronologically (oldest first)
raw_events.sort(key=lambda x: x[0])

# Deduplicate consecutive identical messages & duplicate presses within 1 minute
final_entries = []
last_dt = None
last_desc = None

for dt, desc in raw_events:
    # Skip identical description if within 2 minutes or identical consecutive warning
    if last_dt and last_desc:
        time_diff = (dt - last_dt).total_seconds()
        if desc == last_desc and (time_diff < 120 or 'interval' in desc.lower()):
            continue
        if desc in ['Reset Maintenance'] and last_desc in ['Reset Maintenance'] and time_diff < 120:
            continue

    mtype = 'Maintenance'
    if 'battery' in desc.lower() or 'inspect' in desc.lower() or 'check' in desc.lower():
        mtype = 'Check'
    if desc == 'Reset Maintenance':
        mtype = 'Maintenance'

    entry = {
        "date": dt.strftime('%m/%d/%Y %H:%M'),
        "type": mtype,
        "hours": 0.0,
        "comment": desc
    }
    final_entries.append(entry)
    last_dt = dt
    last_desc = desc

with open(output_json, 'w', encoding='utf-8') as outfile:
    json.dump(final_entries, outfile, indent=4)

print(f"Generated {len(final_entries)} journal entries in {output_json}:")
for e in final_entries:
    print(f"  {e['date']} | {e['type']} | {e['comment']}")
