import os
import csv
import json
from datetime import datetime

csv_path = '/Users/oz/Library/CloudStorage/GoogleDrive-mwoswald@gmail.com/My Drive/Documents/Documents/Owners Manuals and Data Sheets/Generac/Mobilelink Exports/statusHistory.csv'
dl_json = '/Users/oz/Downloads/maintlog.json'
workspace_json = '/Users/oz/Develop/genmon/maintlog.json'

# Load status history rows
status_rows = []
with open(csv_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
    reader = csv.DictReader(f)
    reader.fieldnames = [h.strip() for h in reader.fieldnames]
    for r in reader:
        dt_str = r.get('Date Time', '').strip()
        code = r.get('Status Code', '').strip()
        desc = r.get('Description', '').strip()
        raw_dt = dt_str.split(' America')[0].strip()
        try:
            dt = datetime.strptime(raw_dt, '%m/%d/%Y %I:%M:%S %p')
        except Exception:
            continue
        status_rows.append((dt, code, desc))

status_rows.sort(key=lambda x: x[0])

# Collect outages / manual run sessions for run hours calculation
outages = []
i = 0
while i < len(status_rows):
    dt, code, desc = status_rows[i]
    if 'exercising' in desc.lower():
        i += 1
        continue
    if 'utility loss' in desc.lower() or 'manual' in desc.lower():
        start_t = dt
        end_t = None
        j = i + 1
        while j < len(status_rows):
            dt_next, code_next, desc_next = status_rows[j]
            if desc_next in ['Your generator is ready to run.', 'Switched Off'] or 'stopped' in desc_next.lower() or 'exercising' in desc_next.lower():
                end_t = dt_next
                break
            j += 1
        if end_t:
            dur_sec = (end_t - start_t).total_seconds()
            outages.append((start_t, end_t, dur_sec))
            i = max(j, i + 1)
        else:
            i += 1
    else:
        i += 1

start_origin = datetime(2018, 2, 19)
swap_date = datetime(2026, 6, 20, 23, 59, 59)
target_total_hours = 138.9

def raw_run_hours(t):
    if t < start_origin:
        return 0.0
    outage_sec = sum(dur for s_t, e_t, dur in outages if s_t <= t)
    outage_hrs = outage_sec / 3600.0
    weeks = (t - start_origin).total_seconds() / (7 * 86400.0)
    exercise_hrs = weeks * (5.0 / 60.0)
    return outage_hrs + exercise_hrs

raw_swap_hrs = raw_run_hours(swap_date)
scale_factor = target_total_hours / raw_swap_hrs if raw_swap_hrs > 0 else 1.0

def get_calibrated_hours(t):
    return round(raw_run_hours(t) * scale_factor, 1)

# Load existing maintlog.json entries
with open(dl_json, 'r', encoding='utf-8') as f:
    existing_entries = json.load(f)

# Helper function to parse date string from existing JSON entries
def parse_entry_date(dt_str):
    for fmt in ['%m/%d/%Y %H:%M', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y']:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            pass
    return None

merged_entries = []
seen_keys = set()

# Process existing entries first to preserve their custom types & comments
for e in existing_entries:
    dt = parse_entry_date(e['date'])
    if dt:
        cal_hrs = get_calibrated_hours(dt)
        date_formatted = dt.strftime('%m/%d/%Y %H:%M')
    else:
        cal_hrs = e.get('hours', 0.0)
        date_formatted = e['date']

    entry_key = (date_formatted, e['comment'].strip())
    seen_keys.add(entry_key)

    merged_entries.append({
        "date": date_formatted,
        "type": e['type'],
        "hours": cal_hrs,
        "comment": e['comment'],
        "_dt": dt if dt else datetime.min
    })

# Add remaining statusHistory items classified as "Observation"
new_obs_count = 0
for dt, code, desc in status_rows:
    date_formatted = dt.strftime('%m/%d/%Y %H:%M')
    entry_key = (date_formatted, desc)
    if entry_key in seen_keys:
        continue
    seen_keys.add(entry_key)
    
    cal_hrs = get_calibrated_hours(dt)
    merged_entries.append({
        "date": date_formatted,
        "type": "Observation",
        "hours": cal_hrs,
        "comment": desc,
        "_dt": dt
    })
    new_obs_count += 1

# Sort chronologically by datetime
merged_entries.sort(key=lambda x: x['_dt'])

# Remove helper _dt key before saving
final_json_data = []
for e in merged_entries:
    final_json_data.append({
        "date": e["date"],
        "type": e["type"],
        "hours": e["hours"],
        "comment": e["comment"]
    })

# Save to both Downloads and workspace
for p in [dl_json, workspace_json]:
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, indent=4)

print(f"Merge Complete!")
print(f"  Existing entries processed: {len(existing_entries)}")
print(f"  New Observations added: {new_obs_count}")
print(f"  Total merged entries in maintlog.json: {len(final_json_data)}")
