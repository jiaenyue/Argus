import unittest
from unittest.mock import patch, MagicMock, call
import pandas as pd
import numpy as np
from pathlib import Path
import datetime
import os
import sys

# Ensure src directory is in PYTHONPATH for discovering the collector module
# This is a common pattern for structuring tests.
current_dir = os.path.dirname(os.path.abspath(__file__)) # tests/collectors
collector_module_dir = os.path.dirname(os.path.dirname(current_dir)) # project root
if collector_module_dir not in sys.path:
    sys.path.insert(0, collector_module_dir)

from src.collectors import qmt_collector

class TestQMTCollector(unittest.TestCase):

    def setUp(self):
        # Reset the module-level xtdata mock for each test if needed,
        # or ensure it's patched appropriately within each test.
        # For simplicity, we'll often patch it directly in the test methods.
        self.test_data_path = Path("./temp_unittest_data_storage/qmt")
        # Ensure clean state for file-based tests if any
        if self.test_data_path.exists():
            import shutil
            # shutil.rmtree(self.test_data_path) # Be careful with this in real tests
        self.test_data_path.mkdir(parents=True, exist_ok=True)


    def test_format_stock_code(self):
        self.assertEqual(qmt_collector._format_stock_code("000001"), "000001.SZ")
        self.assertEqual(qmt_collector._format_stock_code("600000"), "600000.SH")
        self.assertEqual(qmt_collector._format_stock_code("830001"), "830001.BJ") # Beijing
        self.assertEqual(qmt_collector._format_stock_code("000001.SZ"), "000001.SZ")
        self.assertEqual(qmt_collector._format_stock_code("600000.SH"), "600000.SH")
        # Test a default case (though behavior might be a warning + default)
        self.assertEqual(qmt_collector._format_stock_code("123456"), "123456.SZ")


    @patch('src.collectors.qmt_collector.xtdata')
    def test_download_historical_data_success(self, mock_xtdata):
        mock_xtdata.download_history_data2 = MagicMock()

        result = qmt_collector.download_historical_data(
            stock_codes="000001.SZ",
            period="1d",
            start_date_str="20230101",
            end_date_str="20230101"
        )
        self.assertTrue(result)
        mock_xtdata.download_history_data2.assert_called_once_with(
            stock_list=["000001.SZ"],
            period="1d",
            start_time="20230101",
            end_time="20230101",
            callback=unittest.mock.ANY # or a specific callback if you define one
        )

    @patch('src.collectors.qmt_collector.xtdata')
    def test_download_historical_data_failure_exception(self, mock_xtdata):
        mock_xtdata.download_history_data2.side_effect = Exception("QMT API Error")

        result = qmt_collector.download_historical_data(
            stock_codes="000001.SZ", period="1d",
            start_date_str="20230101", end_date_str="20230101",
            max_retries=2, retry_delay_seconds=0.01 # Faster retries for test
        )
        self.assertFalse(result)
        self.assertEqual(mock_xtdata.download_history_data2.call_count, 2)

    @patch('src.collectors.qmt_collector.xtdata')
    def test_get_downloaded_data_success(self, mock_xtdata):
        # Mock structure for get_market_data: dict of {field: DataFrame}
        # DataFrame: index=stock_codes, columns=timestamps
        mock_df_open = pd.DataFrame({'20230103093100': [10.0], '20230103093200': [10.1]}, index=["000001.SZ"])
        mock_df_close = pd.DataFrame({'20230103093100': [10.05], '20230103093200': [10.15]}, index=["000001.SZ"])

        mock_xtdata.get_market_data.return_value = {
            'open': mock_df_open,
            'close': mock_df_close,
            # Mock other KLINE_FIELDS as needed or ensure the code handles missing ones
            'high': pd.DataFrame(columns=["000001.SZ"]), # Empty for one field
            'low': mock_df_close.copy(), # just reuse for simplicity
            'volume': mock_df_close.copy(),
            'amount': mock_df_close.copy(),
            'preClose': mock_df_close.copy(),
            'suspendFlag': mock_df_close.copy(),
            'openInterest': mock_df_close.copy(),
            'settelementPrice': mock_df_close.copy(),
        }

        # Reduce KLINE_FIELDS for this specific test to simplify mock
        with patch('src.collectors.qmt_collector.KLINE_FIELDS', ['open', 'close']):
            df = qmt_collector.get_downloaded_data(
                stock_code="000001.SZ", period="1m",
                start_datetime_str="20230103000000", end_datetime_str="20230103235959"
            )

        self.assertIsNotNone(df)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2) # Two timestamps
        self.assertListEqual(list(df.columns), ['open', 'close'])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df.index))

    @patch('src.collectors.qmt_collector.xtdata')
    def test_get_downloaded_data_no_data_returned(self, mock_xtdata):
        mock_xtdata.get_market_data.return_value = {} # Empty dict
        df = qmt_collector.get_downloaded_data("000001.SZ", "1d", "20230101", "20230101")
        self.assertIsNone(df)

        mock_xtdata.get_market_data.return_value = None # API returns None
        df = qmt_collector.get_downloaded_data("000001.SZ", "1d", "20230101", "20230101")
        self.assertIsNone(df)


    @patch('src.collectors.qmt_collector.xtdata')
    def test_get_trading_day_list_success(self, mock_xtdata):
        mock_xtdata.get_trading_dates.return_value = ["20230103", "20230104", "20230105"]
        days = qmt_collector.get_trading_day_list("SH", "20230101", "20230105")
        self.assertEqual(days, ["20230103", "20230104", "20230105"])
        mock_xtdata.get_trading_dates.assert_called_once_with(
            market="SH", start_time="20230101", end_time="20230105", count=-1
        )

    @patch('src.collectors.qmt_collector.xtdata')
    def test_get_trading_day_list_empty(self, mock_xtdata):
        mock_xtdata.get_trading_dates.return_value = []
        days = qmt_collector.get_trading_day_list("SH", "20230101", "20230102") # Range with no trading
        self.assertEqual(days, [])

    @patch('src.collectors.qmt_collector.xtdata')
    def test_get_a_share_stock_list_flow(self, mock_xtdata):
        mock_xtdata.get_sector_list.return_value = ["全部A股", "沪市A股", "深市A股", "其他板块"]

        def mock_get_stock_list_in_sector(sector_name, real_timetag=None):
            if sector_name == "全部A股":
                return ["000001.SZ", "600000.SH", "IGNORETHIS.OTHER"]
            if sector_name == "沪市A股": # Should not be called if "全部A股" works
                return ["600000.SH", "600001.SH"]
            return []
        mock_xtdata.get_stock_list_in_sector.side_effect = mock_get_stock_list_in_sector

        stocks = qmt_collector.get_a_share_stock_list()
        self.assertIn("000001.SZ", stocks)
        self.assertIn("600000.SH", stocks)
        self.assertNotIn("IGNORETHIS.OTHER", stocks)
        self.assertEqual(len(stocks), 2)
        # Check if "全部A股" was prioritized
        self.assertTrue(any("全部A股" in call_args[0] for call_args, _ in mock_xtdata.get_stock_list_in_sector.call_args_list))


    @patch('src.collectors.qmt_collector.fetch_single_stock_day_data')
    @patch('src.collectors.qmt_collector.get_a_share_stock_list')
    @patch('src.collectors.qmt_collector.get_trading_day_list')
    @patch('src.collectors.qmt_collector.download_historical_data') # Mock batch download
    def test_run_collection_basic_flow(self, mock_batch_download, mock_get_trading_days, mock_get_ashares, mock_fetch_single):
        # Setup mocks
        mock_get_trading_days.return_value = ["20230103"]
        mock_get_ashares.return_value = ["000001.SZ", "600000.SH"]

        # Mock return for fetch_single_stock_day_data
        # It returns a dict like {'1d': df_1d, '1m': df_1m}
        mock_df_1d = pd.DataFrame({'close': [10]}, index=[pd.Timestamp("2023-01-03")])
        mock_df_1m = pd.DataFrame({'close': [10.1]}, index=[pd.Timestamp("2023-01-03 09:31:00")])
        mock_fetch_single.return_value = {'1d': mock_df_1d, '1m': mock_df_1m}

        mock_batch_download.return_value = True # Assume batch downloads are successful

        qmt_collector.run_collection(
            start_date_str="20230103",
            end_date_str="20230103",
            base_data_path=self.test_data_path,
            data_types_to_collect=['1d', '1m']
        )

        # Assertions
        mock_get_trading_days.assert_called_once_with("SH", "20230103", "20230103")
        mock_get_ashares.assert_called_once_with(target_date_str="20230103")

        # Check batch download calls
        # Expected: one call for '1d' with all stocks, one for '1m' with all stocks
        self.assertEqual(mock_batch_download.call_count, 2) # 1 for 1d, 1 for 1m
        mock_batch_download.assert_any_call(stock_codes=["000001.SZ", "600000.SH"], period='1d', start_date_str="20230103", end_date_str="20230103")
        mock_batch_download.assert_any_call(stock_codes=["000001.SZ", "600000.SH"], period='1m', start_date_str="20230103", end_date_str="20230103")


        # Check calls to fetch_single_stock_day_data (2 stocks * 1 day)
        self.assertEqual(mock_fetch_single.call_count, 2)
        mock_fetch_single.assert_any_call("000001.SZ", "20230103", data_types=['1d', '1m'])
        mock_fetch_single.assert_any_call("600000.SH", "20230103", data_types=['1d', '1m'])

        # Check if files were created (example for one stock and one period)
        expected_file_1d = self.test_data_path / "1d" / "20230103" / "000001_SZ.parquet"
        expected_file_1m = self.test_data_path / "1m" / "20230103" / "000001_SZ.parquet"
        self.assertTrue(expected_file_1d.exists())
        self.assertTrue(expected_file_1m.exists())

        # Check coverage output (can capture stdout or check logs if using proper logging)
        # For now, we know it ran. Coverage calculation itself is part of run_collection.

    def tearDown(self):
        # Clean up temporary files if any were created directly by tests (not by collector)
        # The collector itself saves to self.test_data_path, which might be inspected manually after tests.
        # Or add logic here to clean it up if desired after each test or test suite.
        import shutil
        if self.test_data_path.exists():
             shutil.rmtree(self.test_data_path) # Clean up test data path
        pass

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

# To run these tests:
# python -m unittest tests.collectors.test_qmt_collector
# or configure your IDE's test runner.
# Make sure xtquant is either installed or qmt_collector.xtdata is None for tests to run (due to the try-except import).
# If xtdata is None, tests relying on its specific mocked methods might need adjustment or will show xtdata is None.
# The @patch decorator effectively replaces qmt_collector.xtdata with a MagicMock for the duration of the test.
```

I also need to create the `__init__.py` files.
