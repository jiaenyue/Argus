# Bronze layer processor
# Consumes data from Kafka, standardizes format, deduplicates, and performs basic type conversions.

import sys
import os
# Add parent directory to path to import event_driven_architecture modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # Attempt to import from the event_driven_architecture package
    from event_driven_architecture.kafka_consumer import consume_from_kafka # Placeholder
    # from event_driven_architecture.event_schema import create_event # Not directly used by processor logic, but good for context
except ImportError:
    print("Error: Could not import Kafka modules from event_driven_architecture. Using fallback consumer.")
    # Fallback dummy consumer if import fails
    def consume_from_kafka(topic, group_id="bronze_group"):
        print(f"Simulating fallback consumption for {topic} by {group_id}")
        return {
            "source": "miniQMT_raw_fallback",
            "timestamp_collected": "2023-10-28T12:00:00Z",
            "data_type": "daily_market_data",
            "payload": {
                "stock_code": "600000", "date": "2023/10/27",
                "open": "10.1", "high": "10.5", "low": "9.8", "close": "10.2", "volume": "1000000"
            }
        }

import datetime
import json

PROCESSED_EVENT_IDS = set()

def get_event_unique_id(event: dict) -> str:
    payload = event.get("payload", {})
    data_type = event.get("data_type")
    if data_type in ["daily_market_data", "minute_market_data"]:
        code = payload.get("stock_code")
        date_val = payload.get("date")
        if code and date_val:
            return f"{data_type}-{code}-{date_val}"
    return json.dumps(payload, sort_keys=True)

def standardize_event(raw_event: dict) -> dict | None:
    # Use a deep copy for the payload to prevent modifying the original event's payload dict
    # This is important if the original event object is used elsewhere after this function.
    # However, a shallow copy of the event itself is fine, we just need to be careful with mutable fields.
    processed_event = raw_event.copy()
    original_payload = processed_event.get("payload", {})
    payload = original_payload.copy() if isinstance(original_payload, dict) else original_payload


    if "date" in payload:
        raw_date = payload["date"]
        # Order of checks is important: datetime.datetime is an instance of datetime.date.
        if isinstance(raw_date, datetime.datetime): # Check for datetime.datetime first
            payload["date"] = raw_date.date().isoformat()
        elif isinstance(raw_date, datetime.date): # Then check for datetime.date
            payload["date"] = raw_date.isoformat()
        elif isinstance(raw_date, str): # Then try to parse if it's a string
            parsed_date = None
            for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    parsed_date = datetime.datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date:
                payload["date"] = parsed_date.isoformat()
            else:
                print(f"Warning: Could not parse date '{raw_date}'. Skipping date standardization.")
        else:
            print(f"Warning: Date field '{raw_date}' is not a recognized string or date type.")

    # Apply the modified payload back to the processed_event
    processed_event["payload"] = payload

    if "stock_code" in payload: # Ensure we are using the 'payload' dict that has been copied and potentially modified
        code = str(payload["stock_code"])
        if '.' not in code:
            if code.startswith('6') and len(code) == 6:
                payload["stock_code"] = f"{code}.SH"
            elif (code.startswith('0') or code.startswith('3')) and len(code) == 6:
                payload["stock_code"] = f"{code}.SZ"
            else:
                print(f"Warning: Stock code '{code}' does not fit SH/SZ pattern. Leaving as is.")

    numeric_fields = ["open", "high", "low", "close", "price"]
    integer_fields = ["volume"]
    for field in numeric_fields:
        if field in payload and isinstance(payload[field], str):
            try:
                payload[field] = float(payload[field])
            except ValueError:
                print(f"Warning: Could not convert '{payload[field]}' to float for field '{field}'.")
    for field in integer_fields:
        if field in payload and isinstance(payload[field], str):
            try:
                payload[field] = int(payload[field])
            except ValueError:
                print(f"Warning: Could not convert '{payload[field]}' to int for field '{field}'.")

    processed_event["payload"] = payload
    processed_event["processing_timestamp_bronze"] = datetime.datetime.utcnow().isoformat() + "Z"
    return processed_event

def process_raw_message_to_bronze(raw_message_topic: str = "raw_data_topic"):
    print(f"Starting Bronze layer processing from topic: {raw_message_topic}")
    raw_event = consume_from_kafka(raw_message_topic, group_id="bronze_processor_group")

    if not raw_event:
        print("No event consumed.")
        return None

    unique_id = get_event_unique_id(raw_event)
    if unique_id in PROCESSED_EVENT_IDS:
        print(f"Event {unique_id} is a duplicate. Skipping.")
        return None

    standardized_event = standardize_event(raw_event)
    if standardized_event:
        PROCESSED_EVENT_IDS.add(unique_id)
        print(f"Successfully processed and standardized event {unique_id}:")
        print(json.dumps(standardized_event, indent=2))
        return standardized_event
    else:
        print(f"Failed to standardize event {unique_id}.")
        return None

if __name__ == "__main__":
    print("Running Bronze Processor (example)...")
    process_raw_message_to_bronze()
    # Simulate a duplicate
    print("\nSimulating duplicate event consumption...")
    process_raw_message_to_bronze()

    # Example with a SZ stock and different date format
    original_consumer = consume_from_kafka
    def consume_sz_example(topic, group_id):
        return {
            "source": "miniQMT_raw_2", "timestamp_collected": "2023-10-28T13:00:00Z",
            "data_type": "daily_market_data",
            "payload": {"stock_code": "000001", "date": "10/27/2023", "open": "12.1", "volume": "500000"}
        }
    consume_from_kafka = consume_sz_example
    print("\nRunning Bronze Processor with SZ stock example...")
    PROCESSED_EVENT_IDS.clear()
    process_raw_message_to_bronze()
    consume_from_kafka = original_consumer # Restore
    print("Bronze Processor script finished.")
