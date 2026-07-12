import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None


_install_stub_module("prefect", task=lambda *args, **kwargs: (lambda func: func))
_install_stub_module("prefect.logging", get_run_logger=lambda: _DummyLogger())
_install_stub_module("dotenv", load_dotenv=lambda: None)
_install_stub_module(
    "usaddress",
    tag=lambda value: ({"StateName": "CA", "ZipCode": "12345"}, "Address"),
    RepeatedLabelError=type("RepeatedLabelError", (Exception,), {}),
)
_install_stub_module(
    "langchain_core.tools", tool=lambda *args, **kwargs: (lambda func: func)
)
_install_stub_module("serpapi", GoogleSearch=lambda *args, **kwargs: None)
_install_stub_module("research_agent", run_agent_sync=lambda *args, **kwargs: None)
_install_stub_module("sql_utils", get_db=lambda: iter([]))

from tables import EventList, EventsSchema
from weekend_short_generation.tasks.event_research_agent.event_research_agent import (
    check_events,
)


def _build_event(index: int) -> dict:
    return EventsSchema(
        event_name=f"Sample Event {index}",
        date="2024-01-01",
        time="10:00 AM",
        location_address="123 Main St, San Francisco, CA 94105",
        description="This is a sample event. " * 200,
        gps_longitude="-122.4194",
        gps_latitude="37.7749",
        url=f"https://example.com/event{index}",
        url_facebook=f"https://facebook.com/event{index}",
        url_instagram=f"https://instagram.com/event{index}",
        keywords="sample, event, trending",
        tiktok_hashtags="#sample,#event,#trending",
        google_trends_query=f"sample event {index}",
        google_trends_value="50",
    )


def test_check_events():
    event_list = EventList(events=[_build_event(i) for i in range(1, 6)])

    res = check_events(events_list=event_list)

    assert res == "success"


def test_check_events_rejects_too_few_events():
    event_list = EventList(events=[_build_event(1)])

    res = check_events(events_list=event_list)

    assert "at least 5 events" in res


def test_check_events_reports_invalid_content():
    event_list = EventList(events=[_build_event(i) for i in range(1, 6)])
    event_list.events[0].description = "short"

    res = check_events(events_list=event_list)

    assert "too short" in res
