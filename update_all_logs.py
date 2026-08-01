import os
import csv
import json
from datetime import datetime

status_file = os.path.expanduser('~/Google Drive/My Drive/Scans/statusHistory.csv')

# Outputs in workspace and downloads
workspace_dir = '/Users/oz/Develop/genmon'
downloads_dir = '/Users/oz/Downloads'

# Load and sort status history
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

# Collect all engine run sessions (Exercising, Utility Loss, Manual)
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

# 1. GENERATE MAINTLOG.JSON
service_keywords = ['battery', 'service', 'reset', 'maintenance', 'inspect', 'repair']
raw_maint = []
for dt, code, desc in rows:
    if any(k in desc.lower() for k in service_keywords):
        raw_maint.append((dt, desc))

raw_maint.sort(key=lambda x: x[0])

maint_entries = []
last_dt = None
last_desc = None

for dt, desc in raw_maint:
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

    run_hrs = get_run_hours(dt)
    maint_entries.append({
        "date": dt.strftime('%m/%d/%Y %H:%M'),
        "type": mtype,
        "hours": run_hrs,
        "comment": desc
    })
    last_dt = dt
    last_desc = desc

# 2. GENERATE OUTAGE.TXT & OUTAGE_SUMMARY.CSV
FUEL_RATE = 200.0  # cu ft / hr (Natural Gas)
FUEL_UNITS = "cubic feet"

outages = []
i = 0
while i < len(rows):
    dt, code, desc = rows[i]
    if 'exercising' in desc.lower():
        i += 1
        continue
    
    if 'utility loss' in desc.lower() or 'manual' in desc.lower():
        start_time = dt
        outage_type = desc
        end_time = None
        j = i + 1
        while j < len(rows):
            dt_next, code_next, desc_next = rows[j]
            if desc_next in ['Your generator is ready to run.', 'Switched Off'] or 'stopped' in desc_next.lower() or 'exercising' in desc_next.lower():
                end_time = dt_next
                break
            j += 1
        
        if end_time:
            duration = end_time - start_time
            outages.append((start_time, end_time, duration, outage_type))
            i = max(j, i + 1)
        else:
            i += 1
    else:
        i += 1

outage_txt_lines = []
outage_summary_rows = []

for start_t, end_t, dur, otype in outages:
    tot_sec = int(dur.total_seconds())
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
    start_run_hrs = get_run_hours(start_t)
    
    # Genmon outage.txt format
    outage_txt_lines.append(f"{start_date_str}, {dur_str}, {fuel_str}")
    
    outage_summary_rows.append({
        "Start Time": start_date_str,
        "End Time": end_t.strftime('%Y-%m-%d %H:%M:%S'),
        "Duration": dur_str,
        "Engine Run Hours": start_run_hrs,
        "Estimated Fuel": fuel_str,
        "Event Type": otype
    })

# Save to workspace and Downloads
paths_to_write = [
    (os.path.join(workspace_dir, 'maintlog.json'), json.dumps(maint_entries, indent=4)),
    (os.path.join(downloads_dir, 'maintlog.json'), json.dumps(maint_entries, indent=4)),
    (os.path.join(workspace_dir, 'outage.txt'), '\n'.join(outage_txt_lines) + '\n'),
    (os.path.join(downloads_dir, 'outage.txt'), '\n'.join(outage_txt_lines) + '\n')
]

for p, content in paths_to_write:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)

# Write summary CSV
for p in [os.path.join(workspace_dir, 'outage_summary.csv'), os.path.join(downloads_dir, 'outage_summary.csv')]:
    with open(p, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["Start Time", "End Time", "Duration", "Engine Run Hours", "Estimated Fuel", "Event Type"])
        writer.writeheader()
        writer.writerows(outage_summary_rows)

print("Updated all files in workspace and ~/Downloads successfully:")
print(f"  maintlog.json : {len(maint_entries)} entries with calculated engine hours")
print(f"  outage.txt     : {len(outage_txt_lines)} outage entries")
print(f"  outage_summary.csv : {len(outage_summary_rows)} rows with Engine Run Hours column")
