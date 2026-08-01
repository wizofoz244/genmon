import os
import csv
import json
from datetime import datetime

status_file = os.path.expanduser('~/Google Drive/My Drive/Scans/statusHistory.csv')
workspace_dir = '/Users/oz/Develop/genmon'
downloads_dir = '/Users/oz/Downloads'

# Load statusHistory.csv rows
rows = []
with open(status_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
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
        rows.append((dt, code, desc))

rows.sort(key=lambda x: x[0])

# Collect all engine run sessions (Exercising, Utility Loss, Manual) to calculate exact run hours
sessions = []
i = 0
while i < len(rows):
    dt, code, desc = rows[i]
    if any(k in desc.lower() for k in ['exercising', 'utility loss', 'manual']):
        start_t = dt
        run_type = desc
        end_t = None
        j = i + 1
        while j < len(rows):
            dt_next, code_next, desc_next = rows[j]
            if desc_next in ['Your generator is ready to run.', 'Switched Off'] or 'stopped' in desc_next.lower():
                end_t = dt_next
                break
            j += 1
        if end_t:
            dur_sec = (end_t - start_t).total_seconds()
            sessions.append((start_t, end_t, dur_sec, run_type))
            i = max(j, i + 1)
        else:
            i += 1
    else:
        i += 1

# Scaling factor to match 138.9 run hours on 06/20/2026
target_dt = datetime(2026, 6, 20, 23, 59, 59)
total_sec_at_target = sum(s[2] for s in sessions if s[0] <= target_dt)
target_hours = 138.9
scale_factor = target_hours / (total_sec_at_target / 3600.0) if total_sec_at_target > 0 else 1.0

def get_run_hours(target_date):
    sec = sum(s[2] for s in sessions if s[0] <= target_date)
    hrs = (sec / 3600.0) * scale_factor
    return round(hrs, 1)

# Raw user-provided text block
user_csv_data = """
Date, Record Type, Maintenance Type, Cost, Run Hours, Notes
07/30/2025, Generator Record, Service B maintenance interval reached, , , 
07/23/2025, Generator Record, Service B maintenance interval reached, , , 
07/16/2025, Generator Record, Service B maintenance interval reached, , , 
07/09/2025, Generator Record, Service B maintenance interval reached, , , 
07/02/2025, Generator Record, Service B maintenance interval reached, , , 
06/25/2025, Generator Record, Service B maintenance interval reached, , , 
06/18/2025, Generator Record, Service B maintenance interval reached, , , 
06/11/2025, Generator Record, Service B maintenance interval reached, , , 
06/05/2025, Generator Record, Service B maintenance interval reached, , , 
06/04/2025, Generator Record, Service B maintenance interval reached, , , 
05/28/2025, Generator Record, Service B maintenance interval reached, , , 
05/21/2025, Generator Record, Service B maintenance interval reached, , , 
05/14/2025, Generator Record, Service B maintenance interval reached, , , 
05/07/2025, Generator Record, Service B maintenance interval reached, , , 
04/30/2025, Generator Record, Service B maintenance interval reached, , , 
04/29/2025, Generator Record, Service B maintenance interval reached, , , 
04/04/2024, Generator Record, Service A maintenance interval reached, , , 
03/13/2024, Generator Record, Service A maintenance interval reached, , , 
03/06/2024, Generator Record, Service A maintenance interval reached, , , 
02/28/2024, Generator Record, Service A maintenance interval reached, , , 
02/21/2024, Generator Record, Service A maintenance interval reached, , , 
02/14/2024, Generator Record, Service A maintenance interval reached, , , 
02/07/2024, Generator Record, Service A maintenance interval reached, , , 
01/31/2024, Generator Record, Service A maintenance interval reached, , , 
01/24/2024, Generator Record, Service A maintenance interval reached, , , 
01/10/2024, Generator Record, Service A maintenance interval reached, , , 
01/03/2024, Generator Record, Service A maintenance interval reached, , , 
12/27/2023, Generator Record, Service A maintenance interval reached, , , 
12/20/2023, Generator Record, Service A maintenance interval reached, , , 
12/13/2023, Generator Record, Service A maintenance interval reached, , , 
12/06/2023, Generator Record, Service A maintenance interval reached, , , 
11/29/2023, Generator Record, Service A maintenance interval reached, , , 
11/22/2023, Generator Record, Service A maintenance interval reached, , , 
11/12/2023, Generator Record, Service A maintenance interval reached, , , 
11/12/2023, Generator Record, Service A maintenance interval reached, , , 
11/08/2023, Generator Record, Service A maintenance interval reached, , , 
11/01/2023, Generator Record, Service A maintenance interval reached, , , 
10/25/2023, Generator Record, Service A maintenance interval reached, , , 
10/18/2023, Generator Record, Service A maintenance interval reached, , , 
10/04/2023, Generator Record, Service A maintenance interval reached, , , 
09/27/2023, Generator Record, Service A maintenance interval reached, , , 
09/20/2023, Generator Record, Service A maintenance interval reached, , , 
09/13/2023, Generator Record, Service A maintenance interval reached, , , 
09/06/2023, Generator Record, Service A maintenance interval reached, , , 
08/30/2023, Generator Record, Service A maintenance interval reached, , , 
08/23/2023, Generator Record, Service A maintenance interval reached, , , 
08/16/2023, Generator Record, Service A maintenance interval reached, , , 
08/09/2023, Generator Record, Service A maintenance interval reached, , , 
08/02/2023, Generator Record, Service A maintenance interval reached, , , 
07/26/2023, Generator Record, Service A maintenance interval reached, , , 
07/22/2023, Generator Record, Service A maintenance interval reached, , , 
07/20/2023, Generator Record, Service A maintenance interval reached, , , 
07/20/2023, Generator Record, Service A maintenance interval reached, , , 
07/19/2023, Generator Record, Service A maintenance interval reached, , , 
07/14/2023, Generator Record, Service A maintenance interval reached, , , 
07/12/2023, Generator Record, Service A maintenance interval reached, , , 
07/08/2023, Generator Record, Service A maintenance interval reached, , , 
07/05/2023, Generator Record, Service A maintenance interval reached, , , 
06/28/2023, Generator Record, Service A maintenance interval reached, , , 
06/21/2023, Generator Record, Service A maintenance interval reached, , , 
06/14/2023, Generator Record, Service A maintenance interval reached, , , 
06/08/2023, Generator Record, Service A maintenance interval reached, , , 
06/08/2023, Generator Record, Service A maintenance interval reached, , , 
06/07/2023, Generator Record, Service A maintenance interval reached, , , 
05/31/2023, Generator Record, Service A maintenance interval reached, , , 
05/24/2023, Generator Record, Service A maintenance interval reached, , , 
05/17/2023, Generator Record, Service A maintenance interval reached, , , 
05/10/2023, Generator Record, Service A maintenance interval reached, , , 
05/03/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
05/02/2023, Generator Record, Service A maintenance interval reached, , , 
04/30/2023, Generator Record, Service A maintenance interval reached, , , 
04/26/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
04/19/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
04/12/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
04/05/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
03/29/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
03/22/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
03/15/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
03/08/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
03/01/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
02/22/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
02/15/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
02/15/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
02/15/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
02/08/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
02/01/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
01/25/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
01/18/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
01/11/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
01/04/2023, Generator Record, Inspect Battery maintenance interval reached, , , 
12/28/2022, Generator Record, Inspect Battery maintenance interval reached, , , 
"""

# Extract maintenance entries from statusHistory.csv as well
service_keywords = ['battery', 'service', 'reset', 'maintenance', 'inspect', 'repair']
all_candidates = []

for dt, code, desc in rows:
    if any(k in desc.lower() for k in service_keywords):
        all_candidates.append((dt, desc))

# Parse the user provided list
reader = csv.DictReader(user_csv_data.strip().splitlines())
reader.fieldnames = [h.strip() for h in reader.fieldnames]

for r in reader:
    date_str = r.get('Date', '').strip()
    mtype_str = r.get('Maintenance Type', '').strip()
    notes_str = r.get('Notes', '').strip()
    if not date_str:
        continue
    try:
        dt = datetime.strptime(date_str, '%m/%d/%Y')
        # set default time to 12:00 if not specified
        dt = dt.replace(hour=12, minute=0, second=0)
    except Exception:
        continue
    
    desc = notes_str if notes_str else mtype_str
    if desc:
        all_candidates.append((dt, desc))

# Sort chronologically (oldest first)
all_candidates.sort(key=lambda x: x[0])

# Clean and deduplicate entries (collapse duplicate entries occurring on same date & description)
final_maint = []
seen = set()

for dt, desc in all_candidates:
    dt_key = (dt.strftime('%Y-%m-%d'), desc.strip())
    if dt_key in seen:
        continue
    seen.add(dt_key)

    mtype = 'Maintenance'
    if 'battery' in desc.lower() or 'inspect' in desc.lower() or 'check' in desc.lower():
        mtype = 'Check'
    if desc == 'Reset Maintenance':
        mtype = 'Maintenance'

    run_hrs = get_run_hours(dt)
    
    final_maint.append({
        "date": dt.strftime('%m/%d/%Y %H:%M'),
        "type": mtype,
        "hours": run_hrs,
        "comment": desc
    })

# Write updated maintlog.json to workspace and Downloads
for p in [os.path.join(workspace_dir, 'maintlog.json'), os.path.join(downloads_dir, 'maintlog.json')]:
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(final_maint, f, indent=4)

print(f"Successfully generated {len(final_maint)} maintenance entries in maintlog.json:")
for e in final_maint[:20]:
    print(f"  {e['date']} | {e['hours']} hrs | {e['type']} | {e['comment']}")
print(f"... and {len(final_maint)-20} more entries.")
