import unittest
from unittest.mock import patch, call
import datetime
import unittest
from unittest.mock import patch, call
import datetime
import sys
import os

# Add parent directory to path to import event_driven_architecture modules and processor
# This allows 'from bronze_layer.processor import ...' to work as if bronze_layer is a package
# and also helps find 'event_driven_architecture' if tests are run from the root or bronze_layer directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bronze_layer.processor import standardize_event, get_event_unique_id, process_raw_message_to_bronze, PROCESSED_EVENT_IDS

# Helper to reset global PROCESSED_EVENT_IDS for test isolation
def reset_processed_ids():
    PROCESSED_EVENT_IDS.clear()

class TestBronzeProcessor(unittest.TestCase):

    def setUp(self):
        reset_processed_ids()
        # Suppress DeprecationWarning from datetime.utcnow() in processor.py during tests
        # This is a bit of a hack; proper logging or conditional warnings in processor.py would be better.
        self.patcher = patch('warnings.warn')
        self.mock_warn = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()


    def test_get_event_unique_id_market_data(self):
        event = {
            "data_type": "daily_market_data",
            "payload": {"stock_code": "600000", "date": "2023/10/27"}
        }
        self.assertEqual(get_event_unique_id(event), "daily_market_data-600000-2023/10/27")

    def test_get_event_unique_id_other_data(self):
        event = {
            "data_type": "some_other_data",
            "payload": {"key": "value", "id": 123}
        }
        # Relies on json.dumps for non-market data
        self.assertEqual(get_event_unique_id(event), '{"id": 123, "key": "value"}')

    def test_standardize_event_date_formats(self):
        event_slash = {"payload": {"date": "2023/10/27"}}
        standardized = standardize_event(event_slash.copy()) # Use copy
        self.assertEqual(standardized["payload"]["date"], "2023-10-27")

        event_dash = {"payload": {"date": "2023-10-27"}}
        standardized = standardize_event(event_dash.copy())
        self.assertEqual(standardized["payload"]["date"], "2023-10-27")

        event_mdy = {"payload": {"date": "10/27/2023"}}
        standardized = standardize_event(event_mdy.copy())
        self.assertEqual(standardized["payload"]["date"], "2023-10-27")

        event_datetime_obj = {"payload": {"date": datetime.datetime(2023, 10, 27, 10, 0, 0)}}
        standardized = standardize_event(event_datetime_obj.copy())
        self.assertEqual(standardized["payload"]["date"], "2023-10-27")

        event_date_obj = {"payload": {"date": datetime.date(2023, 10, 27)}}
        standardized = standardize_event(event_date_obj.copy())
        self.assertEqual(standardized["payload"]["date"], "2023-10-27")

        event_bad_date = {"payload": {"date": "2023-13-01"}} # Invalid month
        with patch('builtins.print') as mock_print:
            standardized = standardize_event(event_bad_date.copy())
            self.assertEqual(standardized["payload"]["date"], "2023-13-01") # Stays as is
            mock_print.assert_any_call("Warning: Could not parse date '2023-13-01'. Skipping date standardization.")

    def test_standardize_event_stock_codes(self):
        event_sh = {"payload": {"stock_code": "600000"}}
        standardized = standardize_event(event_sh.copy())
        self.assertEqual(standardized["payload"]["stock_code"], "600000.SH")

        event_sz0 = {"payload": {"stock_code": "000001"}}
        standardized = standardize_event(event_sz0.copy())
        self.assertEqual(standardized["payload"]["stock_code"], "000001.SZ")

        event_sz3 = {"payload": {"stock_code": "300001"}}
        standardized = standardize_event(event_sz3.copy())
        self.assertEqual(standardized["payload"]["stock_code"], "300001.SZ")

        event_unknown = {"payload": {"stock_code": "830001"}} # Beijing SE
        with patch('builtins.print') as mock_print:
            standardized = standardize_event(event_unknown.copy())
            self.assertEqual(standardized["payload"]["stock_code"], "830001") # Stays as is
            mock_print.assert_any_call("Warning: Stock code '830001' does not fit SH/SZ pattern. Leaving as is.")

        event_already_suffixed = {"payload": {"stock_code": "600000.SH"}}
        standardized = standardize_event(event_already_suffixed.copy())
        self.assertEqual(standardized["payload"]["stock_code"], "600000.SH") # Stays as is

    def test_standardize_event_type_conversion(self):
        event = {
            "payload": {
                "open": "10.5", "volume": "1000", "price": "12.34", "non_numeric": "abc"
            }
        }
        standardized = standardize_event(event.copy())
        self.assertIsInstance(standardized["payload"]["open"], float)
        self.assertEqual(standardized["payload"]["open"], 10.5)
        self.assertIsInstance(standardized["payload"]["volume"], int)
        self.assertEqual(standardized["payload"]["volume"], 1000)
        self.assertIsInstance(standardized["payload"]["price"], float)
        self.assertEqual(standardized["payload"]["price"], 12.34)
        self.assertEqual(standardized["payload"]["non_numeric"], "abc") # Stays as is

        event_bad_numeric = {"payload": {"open": "not-a-number"}}
        with patch('builtins.print') as mock_print:
            standardized = standardize_event(event_bad_numeric.copy())
            self.assertEqual(standardized["payload"]["open"], "not-a-number")
            mock_print.assert_any_call("Warning: Could not convert 'not-a-number' to float for field 'open'.")

    def test_standardize_event_adds_processing_timestamp(self):
        event = {"payload": {"data": "test"}}
        standardized = standardize_event(event.copy())
        self.assertIn("processing_timestamp_bronze", standardized)
        try:
            # Check if it's a valid ISO timestamp
            datetime.datetime.fromisoformat(standardized["processing_timestamp_bronze"].replace("Z", "+00:00"))
        except ValueError:
            self.fail("processing_timestamp_bronze is not a valid ISO timestamp")

    @patch('bronze_layer.processor.consume_from_kafka') # Mock the kafka consumer
    @patch('builtins.print') # Mock print to check log messages
    def test_process_raw_message_to_bronze_new_event(self, mock_print, mock_consume):
        reset_processed_ids() # Ensure clean state for this test
        raw_event = {
            "source": "test_source",
            "timestamp_collected": "2023-01-01T00:00:00Z",
            "data_type": "daily_market_data",
            "payload": {"stock_code": "600000", "date": "2023/01/01", "open": "10.0"}
        }
        mock_consume.return_value = raw_event

        result = process_raw_message_to_bronze("test_topic")

        self.assertIsNotNone(result)
        self.assertEqual(result["payload"]["stock_code"], "600000.SH")
        self.assertEqual(result["payload"]["date"], "2023-01-01")
        self.assertEqual(result["payload"]["open"], 10.0)

        unique_id = get_event_unique_id(raw_event)
        self.assertIn(unique_id, PROCESSED_EVENT_IDS)
        mock_print.assert_any_call(f"Successfully processed and standardized event {unique_id}:")


    @patch('bronze_layer.processor.consume_from_kafka')
    @patch('builtins.print')
    def test_process_raw_message_to_bronze_duplicate_event(self, mock_print, mock_consume):
        reset_processed_ids() # Ensure clean state
        raw_event = {
            "source": "test_source",
            "timestamp_collected": "2023-01-01T00:00:00Z",
            "data_type": "daily_market_data",
            "payload": {"stock_code": "000002", "date": "2023/01/02", "close": "20.0"}
        }
        mock_consume.return_value = raw_event

        # First call - should process
        result1 = process_raw_message_to_bronze("test_topic")
        unique_id = get_event_unique_id(raw_event) # ID from original raw_event
        self.assertIsNotNone(result1)
        self.assertIn(unique_id, PROCESSED_EVENT_IDS)

        # Second call - should be detected as duplicate
        # mock_consume will return the same raw_event again
        result2 = process_raw_message_to_bronze("test_topic")
        self.assertIsNone(result2)
        mock_print.assert_any_call(f"Event {unique_id} is a duplicate. Skipping.")
        self.assertEqual(mock_consume.call_count, 2)


    @patch('bronze_layer.processor.consume_from_kafka')
    def test_process_raw_message_no_event_consumed(self, mock_consume):
        reset_processed_ids()
        mock_consume.return_value = None
        result = process_raw_message_to_bronze("test_topic")
        self.assertIsNone(result)

    @patch('bronze_layer.processor.standardize_event')
    @patch('bronze_layer.processor.consume_from_kafka')
    def test_process_raw_message_standardization_fails(self, mock_consume, mock_standardize_event):
        reset_processed_ids()
        raw_event = {
            "source": "test_source",
            "data_type": "daily_market_data", # Added for unique_id generation
            "payload": {"stock_code": "600003", "date": "2023/01/03"}
        }
        mock_consume.return_value = raw_event
        mock_standardize_event.return_value = None # Simulate failure

        result = process_raw_message_to_bronze("test_topic")
        self.assertIsNone(result)
        unique_id = get_event_unique_id(raw_event)
        self.assertNotIn(unique_id, PROCESSED_EVENT_IDS) # Should not be added if standardization fails


if __name__ == "__main__":
    unittest.main()
