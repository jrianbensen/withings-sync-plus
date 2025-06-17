#!/bin/sh
# Start the proxy-aware server in the background
python /root/server.py &

# Convert existing JSON files to xml on startup
#python /root/converter_xml.py >> /withings/conversion.log 2>&1

# Rename /src/sync.py to /src/sync.py.bak
#mv /src/withings_sync/sync.py /src/withings_sync/sync.py.bak

# Move /root/sync.py to /src/
#cp /root/sync.py /src/withings_sync/


# Add cron jobs
(
  # Withings sync job (every 5 minutes)
  echo "*/5 * * * * withings-sync --fromdate 2025-01-01 --features BLOOD_PRESSURE --to-json --no-upload -v --output /withings/wt_2025_onwards | tee -a /withings/withings.log"

  # JSON to CSV conversion job (every 5 minutes, offset by 1 minute)
  #echo "1-59/5 * * * * python /root/converter_xml.py >> /withings/conversion.log 2>&1"
) | crontab -

# Run crond in the foreground
crond -f -l 6 -L /dev/stdout
