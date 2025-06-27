"""
QMT Data Collector for A-Share Market Data

This module provides functionalities to collect daily and minute-level K-line data
for A-share stocks from the miniQMT (xtdata) API. It includes features for:
- Downloading historical data.
- Retrieving downloaded data and transforming it into pandas DataFrames.
- Fetching lists of A-share stocks.
- Determining trading days.
- Orchestrating the collection process over a date range.
- Saving data to Parquet files.
- Calculating data coverage.

It is designed to be run as part of an Airflow DAG or as a standalone script for
data collection tasks.

Key dependencies: xtquant (for xtdata), pandas, pyarrow.
Ensure miniQMT client is running and accessible.
"""
import datetime
import time
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union

import pandas as pd

# Configure basic logging
# In a larger application, this would be configured externally (e.g., in the Airflow task)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # Output to console
)
logger = logging.getLogger(__name__)


# It's good practice to import xtdata if it's the primary interface,
# though the documentation uses from xtquant import xtdata
try:
    from xtquant import xtdata
except ImportError:
    xtdata = None
    logger.warning("xtquant library not found. QMT functionality will be unavailable.")

# --- Constants ---
QMT_DATE_FORMAT = "%Y%m%d"
QMT_DATETIME_FORMAT = "%Y%m%d%H%M%S"
DEFAULT_BASE_DATA_PATH = Path("./data_storage/qmt")
DEFAULT_TARGET_MARKET_FOR_TRADING_DAYS = "SH" # Shanghai Stock Exchange as reference

# Field lists for K-line data
KLINE_FIELDS = ['time', 'open', 'high', 'low', 'close', 'volume', 'amount',
                'preClose', 'suspendFlag', 'openInterest', 'settelementPrice']


def _format_stock_code(stock_code: str) -> str:
    """
    Ensures stock code is in the format code.market (e.g., "000001.SZ").
    Basic implementation, might need to be more robust if input varies.

    Args:
        stock_code: The stock code string.

    Returns:
        The formatted stock code string.
    """
    if '.' not in stock_code:
        if stock_code.startswith('6') or stock_code.startswith('900'): # SH A-shares, B-shares
            return f"{stock_code}.SH"
        elif stock_code.startswith('0') or stock_code.startswith('200') or stock_code.startswith('300'): # SZ A-shares, B-shares, ChiNext
            return f"{stock_code}.SZ"
        elif stock_code.startswith('4') or stock_code.startswith('8'): # Beijing SE
             return f"{stock_code}.BJ"
        else:
            logger.warning(f"Could not reliably determine market for stock code {stock_code}. Defaulting to SZ. Please verify.")
            return f"{stock_code}.SZ"
    return stock_code


def download_historical_data(
    stock_codes: Union[str, List[str]],
    period: str,
    start_date_str: str,
    end_date_str: str,
    max_retries: int = 3,
    retry_delay_seconds: int = 5
) -> bool:
    """
    Downloads historical K-line data for given stock(s) and period using
    `xtdata.download_history_data2`.

    Args:
        stock_codes: A single stock code or a list of stock codes.
        period: Data period ('1d' for daily, '1m' for 1-minute).
        start_date_str: Start date in "YYYYMMDD" format.
        end_date_str: End date in "YYYYMMDD" format.
        max_retries: Maximum number of retries for the download call.
        retry_delay_seconds: Delay between retries in seconds.

    Returns:
        True if the download API call was successfully initiated, False otherwise.
        Note: Successful initiation does not guarantee all data for all stocks
        in a batch was downloaded by QMT; check QMT client logs or callback messages.
    """
    if xtdata is None:
        logger.error("xtdata module is not available. Cannot download data.")
        return False

    stock_list = [_format_stock_code(sc) for sc in ([stock_codes] if isinstance(stock_codes, str) else stock_codes)]
    if not stock_list:
        logger.warning("Empty stock list provided to download_historical_data.")
        return False

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}: Downloading {period} data for {len(stock_list)} stocks "
                        f"(first: {stock_list[0]}) from {start_date_str} to {end_date_str}...")

            progress_log = []
            def on_progress(data): # QMT's callback
                progress_log.append(data)
                if 'message' in data and data['message'] and \
                   any(err_kw in data['message'].lower() for err_kw in ["错误", "error", "失败"]):
                    logger.warning(f"QMT Download progress message for {data.get('stockcode', 'N/A')}: {data['message']}")

            xtdata.download_history_data2(
                stock_list=stock_list, period=period, start_time=start_date_str,
                end_time=end_date_str, callback=on_progress
            )

            final_errors = [p for p in progress_log if p.get('message') and \
                            any(err_kw in p['message'].lower() for err_kw in ["错误", "error", "失败"])]
            if final_errors:
                 logger.warning(f"Download for period {period}, stocks like {stock_list[0]} completed, but QMT reported "
                                f"{len(final_errors)} issues for some stocks in the batch.")

            logger.info(f"Download call completed for {len(stock_list)} stocks, period {period}.")
            return True
        except Exception as e:
            logger.error(f"Exception during download call for {stock_list[0]} (and others), period {period} "
                         f"(attempt {attempt + 1}): {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay_seconds} seconds...")
                time.sleep(retry_delay_seconds)
            else:
                logger.error(f"Failed to initiate download for {stock_list[0]} (and others), period {period} after {max_retries} attempts.")
                return False
    return False # Should not be reached if max_retries > 0


def get_downloaded_data(
    stock_code: str, period: str, start_datetime_str: str, end_datetime_str: str,
    fields: Optional[List[str]] = None, dividend_type: str = 'none',
    fill_data: bool = True, max_retries: int = 3, retry_delay_seconds: int = 5
) -> Optional[pd.DataFrame]:
    """
    Retrieves downloaded K-line data for a single stock using `xtdata.get_market_data`
    and transforms it into a pandas DataFrame.

    Args:
        stock_code: The stock code (e.g., "000001.SZ").
        period: Data period ('1d', '1m').
        start_datetime_str: Start datetime ("YYYYMMDD" or "YYYYMMDDHHMMSS").
        end_datetime_str: End datetime ("YYYYMMDD" or "YYYYMMDDHHMMSS").
        fields: List of fields to retrieve. Defaults to KLINE_FIELDS.
        dividend_type: Dividend adjustment type ('none', 'front', 'back').
        fill_data: Whether to fill missing data points (QMT default is True).
        max_retries: Maximum number of retries.
        retry_delay_seconds: Delay between retries.

    Returns:
        A pandas DataFrame with a datetime index, or None if an error occurs or no data.
    """
    if xtdata is None:
        logger.error("xtdata module is not available. Cannot retrieve data.")
        return None

    stock_code_formatted = _format_stock_code(stock_code)
    target_fields = fields if fields else KLINE_FIELDS.copy()

    for attempt in range(max_retries):
        try:
            data_dict: Dict[str, pd.DataFrame] = xtdata.get_market_data(
                field_list=target_fields, stock_list=[stock_code_formatted], period=period,
                start_time=start_datetime_str, end_time=end_datetime_str, count=-1,
                dividend_type=dividend_type, fill_data=fill_data
            )

            if not data_dict: return None # No data structure returned
            first_field_df = next(iter(data_dict.values()), None)
            if first_field_df is None or stock_code_formatted not in first_field_df.index:
                # This stock might genuinely have no data for the period in QMT's cache
                return None

            series_list = []
            final_time_index = None
            for field in target_fields:
                if field in data_dict and not data_dict[field].empty and stock_code_formatted in data_dict[field].index:
                    field_series = data_dict[field].loc[stock_code_formatted]
                    if final_time_index is None and not field_series.empty: # Get index from first valid series
                        try: # Robust datetime conversion
                            temp_idx = pd.to_datetime(field_series.index.astype(str), errors='coerce')
                            if not temp_idx.isna().all(): final_time_index = temp_idx
                        except Exception as e_conv:
                            logger.warning(f"Could not parse time index for {stock_code_formatted}, field {field}: {e_conv}")
                    field_series.name = field
                    series_list.append(field_series)

            if not series_list: return None # No valid fields found
            final_df = pd.concat(series_list, axis=1)
            if final_df.empty: return None

            if final_time_index is not None:
                final_df.index = final_time_index
                final_df = final_df[~final_df.index.isna()]
            else: # Fallback if robust conversion failed
                try:
                    final_df.index = pd.to_datetime(final_df.index.astype(str), errors='coerce')
                    final_df = final_df[~final_df.index.isna()]
                except Exception:
                     logger.warning(f"Failed to convert QMT time index for {stock_code_formatted}. Using original numeric index: {final_df.index[:3]}...")
            final_df.index.name = 'datetime'
            return final_df
        except Exception as e:
            logger.error(f"Exception retrieving/processing data for {stock_code_formatted}, period {period} (attempt {attempt + 1}): {e}", exc_info=True)
            if attempt < max_retries - 1: time.sleep(retry_delay_seconds)
            else: return None # Failed after all retries
    return None


def fetch_single_stock_day_data(
    stock_code: str, date_str: str, data_types: List[str] = ['1d', '1m']
) -> Dict[str, Optional[pd.DataFrame]]:
    """
    Fetches specified K-line data types for a single stock on a specific date.
    Orchestrates download and retrieval.

    Args:
        stock_code: The stock code (e.g., "000001.SZ").
        date_str: The target date in "YYYYMMDD" format.
        data_types: List of data types to fetch (e.g., ['1d', '1m']).

    Returns:
        A dictionary where keys are data types ('1d', '1m') and values are
        DataFrames, or None if fetching failed for that type.
    """
    results = {}
    stock_code_fmt = _format_stock_code(stock_code)
    for period in data_types:
        download_start_date, download_end_date = date_str, date_str
        get_start_datetime = f"{date_str}000000" if period == '1m' else date_str
        get_end_datetime = f"{date_str}235959" if period == '1m' else date_str

        # Note: download_historical_data is now batched in run_collection.
        # Calling it here per stock is less efficient but makes this function standalone.
        # For optimal use with run_collection, downloads are done first in batch.
        # However, to ensure data is present if called independently:
        download_successful = download_historical_data(
            stock_codes=stock_code_fmt, period=period,
            start_date_str=download_start_date, end_date_str=download_end_date
        )
        if download_successful: # Or assume download happened if called from run_collection
            results[period] = get_downloaded_data(
                stock_code=stock_code_fmt, period=period,
                start_datetime_str=get_start_datetime, end_datetime_str=get_end_datetime,
                fields=KLINE_FIELDS
            )
        else:
            logger.warning(f"Download initiation failed for {stock_code_fmt}, period {period}, date {date_str}. Skipping retrieval.")
            results[period] = None
    return results

# --- Stock List Retrieval Functions ---
def get_all_sector_names() -> List[str]:
    """Retrieves all available sector names from QMT."""
    if xtdata is None: logger.error("xtdata module is not available."); return []
    try:
        sector_list = xtdata.get_sector_list()
        return [] if sector_list is None else sector_list # API might return None
    except Exception as e:
        logger.error(f"Error getting sector list from QMT: {e}", exc_info=True)
        return []

def get_stocks_in_sector(sector_name: str, date_str: Optional[str] = None) -> List[str]:
    """Retrieves stock codes for a given sector, optionally for a historical date."""
    if xtdata is None: logger.error("xtdata module is not available."); return []
    try:
        stock_list = xtdata.get_stock_list_in_sector(sector_name, real_timetag=date_str)
        if stock_list is None:
            logger.warning(f"xtdata.get_stock_list_in_sector returned None for sector '{sector_name}' (date: {date_str or 'latest'}).")
            return []
        return [_format_stock_code(sc) for sc in stock_list]
    except Exception as e:
        logger.error(f"Error getting stock list for sector {sector_name}: {e}", exc_info=True)
        return []

def get_a_share_stock_list(target_date_str: Optional[str] = None) -> List[str]:
    """
    Attempts to get a list of all A-share stock codes for a target date.
    Checks common A-share sector names and combines them if necessary.

    Args:
        target_date_str: Optional date "YYYYMMDD" for historical constituents. None for latest.

    Returns:
        A sorted list of unique A-share stock codes (e.g., "000001.SZ").
    """
    if xtdata is None: logger.error("xtdata module is not available."); return []

    all_sectors = get_all_sector_names()
    # Prioritize comprehensive sector names
    comprehensive_patterns = ["全部A股", "A股市场", "A股"]
    potential_ashare_sectors = [s for s in all_sectors if any(p in s for p in comprehensive_patterns)] if all_sectors else comprehensive_patterns

    all_a_shares = set()
    if potential_ashare_sectors:
        for sector in potential_ashare_sectors:
            logger.debug(f"Trying comprehensive sector: '{sector}' for date {target_date_str or 'latest'}")
            stocks = get_stocks_in_sector(sector, date_str=target_date_str)
            if stocks: all_a_shares.update(stocks)

    # Fallback to specific market segments if comprehensive list is empty or not found
    if not all_a_shares:
        logger.info("No stocks found via comprehensive A-share sectors, trying market segments.")
        market_segment_sectors = []
        if all_sectors:
            sh_patterns = ["沪市A", "上证A", "SHAA", "上海A股"]
            sz_patterns = ["深市A", "深证A", "SZAA", "深圳A股"]
            bj_patterns = ["北证A", "北交所A股", "BJAA", "北交所"] # Added "北交所"

            market_segment_sectors.extend([s for s in all_sectors if any(p in s for p in sh_patterns)])
            market_segment_sectors.extend([s for s in all_sectors if any(p in s for p in sz_patterns)])
            market_segment_sectors.extend([s for s in all_sectors if any(p in s for p in bj_patterns)])
            market_segment_sectors = sorted(list(set(market_segment_sectors))) # Unique and sorted

        if not market_segment_sectors : # Absolute fallback if no matching sectors found
             market_segment_sectors = ["沪市A股", "深市A股", "科创板", "创业板", "北交所"]
             logger.warning(f"No specific A-share market segments identified in QMT's list, using fallback guesses: {market_segment_sectors}")

        for sector_name in market_segment_sectors:
            logger.debug(f"Fetching stocks for segment: '{sector_name}' for date {target_date_str or 'latest'}")
            stocks = get_stocks_in_sector(sector_name, date_str=target_date_str)
            all_a_shares.update(stocks)

    # Filter for valid A-share suffixes
    final_list = sorted([s for s in list(all_a_shares) if s.endswith((".SZ", ".SH", ".BJ"))])
    logger.info(f"Found {len(final_list)} unique A-share stock codes for date {target_date_str or 'latest'}.")
    return final_list

# --- Trading Day Retrieval Functions ---
def get_trading_day_list(market_code: str, start_date_str: str, end_date_str: str) -> List[str]:
    """
    Retrieves a list of trading days for a given market and date range.
    """
    if xtdata is None: logger.error(f"xtdata module not available for market {market_code}."); return []
    try:
        logger.debug(f"Fetching trading days for market {market_code} from {start_date_str} to {end_date_str}...")
        trading_days = xtdata.get_trading_dates(market=market_code, start_time=start_date_str, end_time=end_date_str, count=-1)
        if trading_days is None:
            logger.warning(f"xtdata.get_trading_dates returned None for market {market_code}.")
            return []
        valid_trading_days = sorted([day for day in trading_days if day and isinstance(day, str)])
        logger.debug(f"Found {len(valid_trading_days)} trading days for market {market_code} in the range.")
        return valid_trading_days
    except Exception as e:
        logger.error(f"Error getting trading days for market {market_code}: {e}", exc_info=True)
        return []

# --- Main Collection Orchestration ---
def run_collection(
    start_date_str: str, end_date_str: str,
    base_data_path: Union[str, Path] = DEFAULT_BASE_DATA_PATH,
    target_market_for_trading_days: str = DEFAULT_TARGET_MARKET_FOR_TRADING_DAYS,
    data_types_to_collect: List[str] = ['1d', '1m'],
    batch_size_stocks_download: int = 100
):
    """
    Orchestrates the collection of K-line data for A-share stocks for a given date range.

    Saves data to Parquet files under:
    `base_data_path / period_type / YYYYMMDD / STOCK_CODE.parquet`

    Args:
        start_date_str: Start date of collection period ("YYYYMMDD").
        end_date_str: End date of collection period ("YYYYMMDD").
        base_data_path: Base directory to save Parquet files.
        target_market_for_trading_days: Market code (e.g., "SH") to use for fetching trading days.
        data_types_to_collect: List of data types to fetch (e.g., ['1d', '1m']).
        batch_size_stocks_download: Number of stocks to include in a single download batch.
    """
    if xtdata is None: logger.critical("xtdata module not available. Collection cannot run."); return

    base_data_path = Path(base_data_path)
    logger.info(f"Starting data collection from {start_date_str} to {end_date_str}.")
    logger.info(f"Data will be saved under: {base_data_path.resolve()}")

    collection_trading_days = get_trading_day_list(target_market_for_trading_days, start_date_str, end_date_str)
    if not collection_trading_days:
        logger.warning(f"No trading days found for market {target_market_for_trading_days} "
                       f"between {start_date_str} and {end_date_str}. Exiting.")
        return
    logger.info(f"Identified {len(collection_trading_days)} trading days for collection: {collection_trading_days}")

    total_expected_datapoints = 0
    total_successful_datapoints = 0

    for trading_day in collection_trading_days:
        logger.info(f"===== Processing data for trading day: {trading_day} =====")
        logger.info(f"Fetching A-share stock list for {trading_day}...")
        current_day_stock_list = get_a_share_stock_list(target_date_str=trading_day)

        if not current_day_stock_list:
            logger.warning(f"No A-share stocks found for {trading_day}. Skipping this day.")
            continue
        logger.info(f"Found {len(current_day_stock_list)} A-share stocks for {trading_day}. First few: {current_day_stock_list[:5]}")

        total_expected_datapoints += len(current_day_stock_list) * len(data_types_to_collect)

        # Batch download for all stocks for this day and each data type
        for period_to_download in data_types_to_collect:
            logger.info(f"--- Batch downloading {period_to_download} data for all {len(current_day_stock_list)} stocks on {trading_day} ---")
            all_stocks_for_period = current_day_stock_list.copy() # Use a copy for potential modifications

            for i in range(0, len(all_stocks_for_period), batch_size_stocks_download):
                stock_batch = all_stocks_for_period[i:i + batch_size_stocks_download]
                logger.debug(f"Downloading batch {i // batch_size_stocks_download + 1} for {period_to_download} on {trading_day} ({len(stock_batch)} stocks)...")
                # download_historical_data already logs its own success/failure details
                download_historical_data(
                    stock_codes=stock_batch, period=period_to_download,
                    start_date_str=trading_day, end_date_str=trading_day
                )
            logger.info(f"All download batches for {period_to_download} on {trading_day} initiated.")

        # Retrieve and save data for each stock individually
        for i, stock_code in enumerate(current_day_stock_list):
            if (i + 1) % 50 == 0 or i == 0 or (i + 1) == len(current_day_stock_list) :
                logger.info(f"Processing stock {i+1}/{len(current_day_stock_list)}: {stock_code} for day {trading_day}")

            fetched_data_for_stock = fetch_single_stock_day_data(stock_code, trading_day, data_types=data_types_to_collect)

            for period, df in fetched_data_for_stock.items():
                if df is not None and not df.empty:
                    total_successful_datapoints += 1
                    try:
                        safe_stock_code_fn = stock_code.replace(".", "_")
                        period_path = base_data_path / period / trading_day
                        period_path.mkdir(parents=True, exist_ok=True)
                        file_path = period_path / f"{safe_stock_code_fn}.parquet"
                        df.to_parquet(file_path, engine='pyarrow', index=True)
                        logger.debug(f"Saved {period} data for {stock_code} on {trading_day} to {file_path}")
                    except Exception as e_save:
                        logger.error(f"Error saving Parquet for {stock_code}, {period}, {trading_day}: {e_save}", exc_info=True)
                        # Decrement if save failure means not successful by FR-001 criteria
                        # total_successful_datapoints -=1
                else:
                    logger.warning(f"No {period} data fetched or data was empty for {stock_code} on {trading_day}.")
        logger.info(f"===== Finished processing for trading day: {trading_day} =====")

    logger.info("Data collection run finished.")
    # --- Coverage Calculation ---
    if total_expected_datapoints > 0:
        coverage_percentage = (total_successful_datapoints / total_expected_datapoints) * 100
        logger.info("--- Data Collection Coverage Report ---")
        logger.info(f"Total Trading Days Processed: {len(collection_trading_days)}")
        logger.info(f"Total Expected Data Points (Stock-Day-Period level): {total_expected_datapoints}")
        logger.info(f"Total Successfully Fetched Data Points (Stock-Day-Period level): {total_successful_datapoints}")
        logger.info(f"Overall Data Coverage: {coverage_percentage:.2f}%")
        if coverage_percentage >= 99.5:
            logger.info("Coverage meets FR-001 target (>= 99.5%).")
        else:
            logger.warning("Coverage is BELOW FR-001 target (>= 99.5%). Consider investigating missing data.")
    else:
        logger.info("--- Data Collection Coverage Report ---")
        logger.info("No data points were expected (e.g., no trading days or no stocks found). Coverage not applicable.")

if __name__ == '__main__':
    logger.info("Starting QMT Collector Test Script (running as __main__)...")
    if xtdata is None: logger.critical("xtdata module not loaded. Exiting test."); exit(1)

    # Configure for a short test run
    test_run_start_date = (datetime.date.today() - datetime.timedelta(days=3)).strftime(QMT_DATE_FORMAT) # Recent 3 days ago
    test_run_end_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime(QMT_DATE_FORMAT)   # Up to yesterday

    # Ensure start_date is not after end_date, especially around month/year ends with fixed timedelta days
    start_dt = datetime.datetime.strptime(test_run_start_date, QMT_DATE_FORMAT)
    end_dt = datetime.datetime.strptime(test_run_end_date, QMT_DATE_FORMAT)
    if start_dt > end_dt:
        logger.warning(f"Adjusted test_run_start_date as it was after end_date. Original start: {test_run_start_date}")
        test_run_start_date = test_run_end_date # Run for a single day if range is inverted

    logger.info(f"--- Test Full Collection Run for {test_run_start_date} to {test_run_end_date} ---")
    test_data_path = Path("./temp_test_data_storage/qmt_main_run") # Different path for main test
    logger.info(f"Test data will be saved under: {test_data_path.resolve()}")

    # Optional: Clean up test directory before run
    # if test_data_path.exists():
    #     import shutil
    #     logger.info(f"Removing existing test data directory: {test_data_path}")
    #     shutil.rmtree(test_data_path)

    run_collection(
        start_date_str=test_run_start_date, end_date_str=test_run_end_date,
        base_data_path=test_data_path,
        batch_size_stocks_download=50, # Smaller batch for testing
        target_market_for_trading_days="SH" # Explicitly set for test
    )
    logger.info(f"--- Full Collection Run Test Finished. Check output in {test_data_path.resolve()} ---")
    logger.info("QMT Collector Test Script (running as __main__) Finished.")
