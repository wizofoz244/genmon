import os
import csv
import sys
from datetime import datetime

# Default configuration (can be adjusted via arguments or script variables)
# Default assumes Natural Gas with 200.0 cu ft/hr @ 50% load (typical 22kW generator)
# Or Liquid Propane with 2.1 gal/hr @ 50% load
FUEL_TYPE = "Natural Gas"  # Options: "Natural Gas", "Propane", "Diesel"
FUEL_UNITS = "cubic feet"  # Options: "cubic feet", "gal", "L"
HALF_LOAD_RATE = 200.0     # Fuel consumption per hour at 50% load

if len(sys.argv) > 1:
    FUEL_TYPE = sys.argv[1]
if len(sys.argv) > 2:
    try:
        HALF_LOAD_RATE = float(sys.argv[2])
    except ValueError:
        pass
if len(sys.argv) > 3:
    FUEL_UNITS = sys.argv[3]

csv_path = os.path.expanduser('~/Google Drive/My Drive/Scans/statusHistory.csv')
output_txt = '/Users/oz/Develop/genmon/outage.txt'
output_summary_csv = '/Users/oz/Develop/genmon/outage_summary.csv'

rows = []
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
        rows.append((dt, code, desc))

rows.sort(key=lambda x: x[0])

outages = []

i = 0
while i < len(rows):
    dt, code, desc = rows[i]
    # EXCLUDE exercise sessions
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
summary_rows = []
total_fuel_used = 0.0

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
    
    # Calculate estimated fuel used for this outage
    dur_hours = tot_sec / 3600.0
    fuel_used = round(dur_hours * HALF_LOAD_RATE, 2)
    total_fuel_used += fuel_used
    
    fuel_str = f"{fuel_used:.2f} {FUEL_UNITS}"
    date_str = start_t.strftime('%Y-%m-%d %H:%M:%S')
    
    # Genmon outage.txt format: YYYY-MM-DD HH:MM:SS, Duration, FuelUsed
    outage_txt_lines.append(f"{date_str}, {dur_str}, {fuel_str}")
    
    summary_rows.append({
        "Start Time": date_str,
        "End Time": end_t.strftime('%Y-%m-%d %H:%M:%S'),
        "Duration": dur_str,
        "Estimated Fuel": fuel_str,
        "Event Type": otype
    })

# Write outage.txt
with open(output_txt, 'w', encoding='utf-8') as f:
    f.write('\n'.join(outage_txt_lines) + '\n')

# Write summary CSV
with open(output_summary_csv, 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["Start Time", "End Time", "Duration", "Estimated Fuel", "Event Type"])
    writer.writeheader()
    writer.writerows(summary_rows)

print(f"Processed {len(outage_txt_lines)} non-exercise outages/runs.")
print(f"Fuel Rate: {HALF_LOAD_RATE} {FUEL_UNITS}/hr ({FUEL_TYPE})")
print(f"Total Cumulative Fuel Used: {total_fuel_used:.2f} {FUEL_UNITS}")
