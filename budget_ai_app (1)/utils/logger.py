# utils/logger.py
import csv
import time
from pathlib import Path
from typing import Dict, Any

def log_freeze_request(record: Dict[str, Any], path: str = "logs/freeze_requests.csv") -> None:
    """
    Append a freeze/SMS event to a CSV logfile.
    record keys expected: index, date, description, amount, sms_sent (bool), sms_info (str)
    """
    Path("logs").mkdir(exist_ok=True)
    header = ["timestamp", "index", "date", "description", "amount", "sms_sent", "sms_info"]
    write_header = not Path(path).exists()

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            record.get("index", ""),
            record.get("date", ""),
            record.get("description", ""),
            record.get("amount", ""),
            record.get("sms_sent", False),
            record.get("sms_info", "")
        ])
