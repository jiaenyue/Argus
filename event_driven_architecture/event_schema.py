# Defines the standard event schema for data published to Kafka.

from typing import Dict, Any, Literal

# Using TypedDict for better type hinting, if available and desired
# from typing import TypedDict
# class Event(TypedDict):
#     source: str
#     timestamp_collected: str # ISO 8601 format, e.g., "2023-10-27T10:00:00Z"
#     data_type: Literal["daily_market_data", "minute_market_data", "other"] # Example data types
#     payload: Dict[str, Any]

def create_event(source: str, data_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a standard event object.

    Args:
        source (str): The origin of the data (e.g., "miniQMT", "other_source").
        data_type (str): Type of data (e.g., "daily_market_data", "minute_market_data").
        payload (Dict[str, Any]): The actual data payload.

    Returns:
        Dict[str, Any]: The structured event.
    """
    import datetime
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

    event = {
        "source": source,
        "timestamp_collected": timestamp,
        "data_type": data_type,
        "payload": payload
    }
    # Basic validation (can be expanded with a proper schema validation library like Pydantic)
    if not all([source, data_type, payload is not None]):
        raise ValueError("Source, data_type, and payload are required for an event.")
    return event

if __name__ == "__main__":
    # Example usage
    try:
        sample_payload = {
            "stock_code": "600001.SH",
            "date": "2023-10-27",
            "open": 12.0,
            "close": 12.5
        }
        event_object = create_event(
            source="miniQMT_collector",
            data_type="daily_market_data",
            payload=sample_payload
        )
        print("Created event:")
        import json
        print(json.dumps(event_object, indent=2))

        # Example of how this event would be used with the producer
        # from kafka_producer import send_to_kafka (assuming in same directory for this example)
        # if send_to_kafka("raw_data_topic", event_object):
        #     print("Event successfully sent to Kafka.")
        # else:
        #     print("Failed to send event to Kafka.")

    except ValueError as e:
        print(f"Error creating event: {e}")
    except ImportError:
        print("Note: kafka_producer not found for direct sending example, which is fine for schema definition.")
