import os
import csv
import json
from datetime import datetime

status_file = os.path.expanduser('~/Google Drive/My Drive/Scans/statusHistory.csv')
workspace_dir = '/Users/oz/Develop/genmon'
downloads_dir = '/Users/oz/Downloads'

# Load statusHistory.csv
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

# Collect outages / manual run sessions
outages = []
i = 0
while i < len(rows):
    dt, code, desc = rows[i]
    if 'exercising' in desc.lower():
        i += 1
        continue
    if 'utility loss' in desc.lower() or 'manual' in desc.lower():
        start_t = dt
        outage_type = desc
        end_t = None
        j = i + 1
        while j < len(rows):
            dt_next, code_next, desc_next = rows[j]
            if desc_next in ['Your generator is ready to run.', 'Switched Off'] or 'stopped' in desc_next.lower() or 'exercising' in desc_next.lower():
                end_t = dt_next
                break
            j += 1
        if end_t:
            dur_sec = (end_t - start_t).total_seconds()
            outages.append((start_t, end_t, dur_sec, outage_type))
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
    outage_sec = sum(dur for s_t, e_t, dur, _ in outages if s_t <= t)
    outage_hrs = outage_sec / 3600.0
    weeks = (t - start_origin).total_seconds() / (7 * 86400.0)
    exercise_hrs = weeks * (5.0 / 60.0)
    return outage_hrs + exercise_hrs

raw_swap_hrs = raw_run_hours(swap_date)
scale_factor = target_total_hours / raw_swap_hrs if raw_swap_hrs > 0 else 1.0

def get_calibrated_hours(t):
    return round(raw_run_hours(t) * scale_factor, 1)

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

service_keywords = ['battery', 'service', 'reset', 'maintenance', 'inspect', 'repair']
all_candidates = []

for dt, code, desc in rows:
    if any(k in desc.lower() for k in service_keywords):
        all_candidates.append((dt, desc))

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
        dt = dt.replace(hour=12, minute=0, second=0)
    except Exception:
        continue
    desc = notes_str if notes_str else mtype_str
    if desc:
        all_candidates.append((dt, desc))

all_candidates.sort(key=lambda x: x[0])

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

    run_hrs = get_calibrated_hours(dt)
    
    final_maint.append({
        "date": dt.strftime('%m/%d/%Y %H:%M'),
        "type": mtype,
        "hours": run_hrs,
        "comment": desc
    })

# Outage log summary
FUEL_RATE = 200.0
FUEL_UNITS = "cubic feet"
outage_txt_lines = []
outage_summary_rows = []

for start_t, end_t, dur_sec, otype in outages:
    tot_sec = int(dur_sec)
    hours = tot_sec // 3600
    minutes = (tot_sec % 3600) // 60
    seconds = tot_sec % 60
    
    if hours >= 24:
        days = hours // 24
        hours = hours % 24
        dur_str = f"{days} day, {hours}:{minutes:02d}:{seconds:02d}"
    else:
        dur_str = f"{hours}:{minutes:02d}:{seconds:02d}"
    
    dur_hours = tot_sec / 3600.0
    fuel_used = round(dur_hours * FUEL_RATE, 2)
    fuel_str = f"{fuel_used:.2f} {FUEL_UNITS}"
    start_date_str = start_t.strftime('%Y-%m-%d %H:%M:%S')
    start_run_hrs = get_calibrated_hours(start_t)
    
    outage_txt_lines.append(f"{start_date_str}, {dur_str}, {fuel_str}")
    outage_summary_rows.append({
        "Start Time": start_date_str,
        "End Time": end_t.strftime('%Y-%m-%d %H:%M:%S'),
        "Duration": dur_str,
        "Engine Run Hours": start_run_hrs,
        "Estimated Fuel": fuel_str,
        "Event Type": otype
    })

# Save output files to workspace and Downloads
for p in [os.path.join(workspace_dir, 'maintlog.json'), os.path.join(downloads_dir, 'maintlog.json')]:
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(final_maint, f, indent=4)

for p in [os.path.join(workspace_dir, 'outage.txt'), os.path.join(downloads_dir, 'outage.txt')]:
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(outage_txt_lines) + '\n')

for p in [os.path.join(workspace_dir, 'outage_summary.csv'), os.path.join(downloads_dir, 'outage_summary.csv')]:
    with open(p, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["Start Time", "End Time", "Duration", "Engine Run Hours", "Estimated Fuel", "Event Type"])
        writer.writeheader()
        writer.writerows(outage_summary_rows)

print(f"Recalculated all files incorporating weekly 5-min exercises:")
print(f"  maintlog.json : {len(final_maint)} entries")
print(f"  outage.txt     : {len(outage_txt_lines)} entries")
print(f"  outage_summary.csv : {len(outage_summary_rows)} rows")
