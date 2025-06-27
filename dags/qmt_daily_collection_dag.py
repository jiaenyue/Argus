from __future__ import annotations

import pendulum
import datetime

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

# Assuming qmt_collector.py is in a location accessible by PYTHONPATH
# e.g., if dags/ and src/ are sibling directories and src/ is in PYTHONPATH
# Or, if the project is installed as a package.
# For robust imports in Airflow, packaging the project or adjusting PYTHONPATH in Airflow's environment is key.
try:
    from src.collectors import qmt_collector
except ImportError:
    # This is a fallback for local development or if PYTHONPATH is not set in Airflow yet.
    # It assumes 'dags' and 'src' are siblings.
    import sys
    import os
    # Add the parent directory of 'dags' to sys.path, then can import src.collectors
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from src.collectors import qmt_collector


def run_qmt_collection_for_previous_trading_day():
    """
    Callable function for the PythonOperator.
    Determines the previous trading day and calls the main collection script.
    """
    if qmt_collector.xtdata is None:
        raise ConnectionError("xtdata module (miniQMT client) is not available or not connected. DAG cannot run.")

    # Determine the execution date (logical date in Airflow)
    # For a daily DAG, execution_date is typically the start of the period it's covering.
    # If DAG runs at 2023-01-02 00:00:00 for data of 2023-01-01,
    # then we need to find the trading day that is 2023-01-01 or earlier.

    # Let's aim to collect for T-1 (previous actual day, if it was a trading day)
    # Or, more robustly, find the latest trading day before "today" (physical today).
    # Airflow's execution_date might be more suitable for backfills.
    # For simplicity for now: find the last trading day prior to today.

    today_phys = datetime.date.today()
    # Look for the last trading day up to yesterday.
    # Market 'SH' is used as a reference; A-share markets usually have synchronized trading days.
    # Adjust market if needed.
    try:
        # Get the most recent trading day ending yesterday.
        # end_time is inclusive for get_trading_dates.
        # We want the latest trading day that has already passed.
        yesterday_str = (today_phys - datetime.timedelta(days=1)).strftime(qmt_collector.QMT_DATE_FORMAT)

        # Fetch last 1 trading day based on Shanghai market, ending yesterday.
        # This should give the most recent completed trading day.
        latest_trading_days = qmt_collector.xtdata.get_trading_dates(
            market='SH',
            end_time=yesterday_str,
            count=1
        )

        if not latest_trading_days:
            print(f"No trading days found up to {yesterday_str}. Skipping collection.")
            # This could happen on a Monday morning if xtdata hasn't updated for Friday yet,
            # or if it's a long holiday. Consider alerting or specific handling.
            return

        target_collection_date = latest_trading_days[0]
        print(f"Determined target collection date (previous trading day): {target_collection_date}")

    except Exception as e:
        print(f"Error determining previous trading day: {e}")
        # Fallback or raise error to make Airflow task fail
        # For now, let's make it fail to ensure issues are visible.
        raise ValueError(f"Could not determine the previous trading day due to: {e}")


    # Call the main collection function from qmt_collector
    # The base_data_path will use the default from qmt_collector
    print(f"Calling run_collection for date: {target_collection_date}")
    qmt_collector.run_collection(
        start_date_str=target_collection_date,
        end_date_str=target_collection_date,
        # base_data_path can be configured via Airflow variables if needed
        # target_market_for_trading_days can also be configured
    )
    print(f"Finished qmt_collector.run_collection for date: {target_collection_date}")


with DAG(
    dag_id="qmt_daily_market_data_collection",
    start_date=pendulum.datetime(2023, 1, 1, tz="Asia/Shanghai"), # Adjust start date as needed
    schedule="0 8 * * *",  # Run daily at 8:00 AM (Asia/Shanghai time)
                           # QMT data is usually available well before market open, or after market close for previous day.
                           # Adjust schedule based on when QMT data for T-1 is reliably available.
                           # E.g., after market close (17:00) or early next morning.
    catchup=False, # Set to True if you want to backfill for past missed schedules
    tags=["data-collection", "qmt", "market-data"],
    doc_md="""\
    ### QMT Daily Market Data Collection DAG

    This DAG collects daily ('1d') and 1-minute ('1m') K-line data for all A-share stocks
    from the miniQMT data source.

    - **Schedule**: Runs daily.
    - **Target**: Collects data for the most recent completed trading day (T-1).
    - **Output**: Parquet files stored in the configured data storage path.
    - **Coverage Goal**: 99.5% (FR-001).
    """,
) as dag:
    collect_qmt_data_task = PythonOperator(
        task_id="collect_ashare_daily_and_minute_kline",
        python_callable=run_qmt_collection_for_previous_trading_day,
        # provide_context=True, # if you need access to {{ ds }}, {{ execution_date }} etc.
                               # but here we calculate T-1 based on physical date.
    )
