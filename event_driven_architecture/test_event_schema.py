import unittest
import datetime
from event_schema import create_event

class TestEventSchema(unittest.TestCase):

    def test_create_event_success(self):
        source = "test_source"
        data_type = "test_data"
        payload = {"key": "value"}

        event = create_event(source, data_type, payload)

        self.assertEqual(event["source"], source)
        self.assertEqual(event["data_type"], data_type)
        self.assertEqual(event["payload"], payload)
        self.assertIn("timestamp_collected", event)

        # Check if timestamp is in ISO 8601 format and close to now
        try:
            datetime.datetime.fromisoformat(event["timestamp_collected"].replace("Z", "+00:00"))
            # Further check if it's recent, e.g., within the last few seconds
            timestamp_dt = datetime.datetime.fromisoformat(event["timestamp_collected"].replace("Z", ""))
            now_utc = datetime.datetime.utcnow()
            self.assertTrue(abs((now_utc - timestamp_dt).total_seconds()) < 5) # Within 5 seconds
        except ValueError:
            self.fail("timestamp_collected is not in valid ISO 8601 format")

    def test_create_event_missing_source(self):
        with self.assertRaises(ValueError):
            create_event(source="", data_type="test_data", payload={"key": "value"})

    def test_create_event_missing_data_type(self):
        with self.assertRaises(ValueError):
            create_event(source="test_source", data_type="", payload={"key": "value"})

    def test_create_event_missing_payload(self):
        # In the current implementation, an empty dict is a valid payload.
        # If None payload should raise error, the create_event function needs modification.
        # For now, this test assumes None payload is an issue based on "payload is not None" check.
        # However, the type hint Dict[str, Any] suggests payload should always be a dict.
        # Let's refine create_event to be more explicit or adjust this test.
        # Current check: `if not all([source, data_type, payload is not None]):`
        # This means payload=None would raise ValueError.
        with self.assertRaises(ValueError):
            create_event(source="test_source", data_type="test_data", payload=None)

if __name__ == "__main__":
    unittest.main()
