"""
Stage A Ingestion Adapters and Anomaly Detectors.
Supports GDACS, GDELT/RSS, IMD Weather, and IMF PortWatch AIS series.
"""

from asci.ingestion.base import FeedAdapter, RawSignal, quote_untrusted_text
from asci.ingestion.gdacs_adapter import GDACSAdapter
from asci.ingestion.gdelt_rss_adapter import GDELTRSSAdapter
from asci.ingestion.imd_weather_adapter import IMDWeatherAdapter
from asci.ingestion.portwatch_detector import PortWatchAnomalyDetector

__all__ = [
    "FeedAdapter",
    "GDACSAdapter",
    "GDELTRSSAdapter",
    "IMDWeatherAdapter",
    "PortWatchAnomalyDetector",
    "RawSignal",
    "quote_untrusted_text",
]

