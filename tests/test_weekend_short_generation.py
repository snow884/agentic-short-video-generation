import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEEKEND_SHORT_ROOT = SRC / "weekend_short_generation"
for path in [str(SRC), str(WEEKEND_SHORT_ROOT)]:
    if path not in sys.path:
        sys.path.insert(0, path)


class DummyLogger:
    def info(self, message):
        return message


class DummySession:
    def __init__(self):
        self._model_name = None

    def query(self, model):
        self._model_name = getattr(model, "__name__", str(model))
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self._model_name == "Towns":
            return type("Row", (), {"name": "Sample Town"})()
        if self._model_name == "Weekends":
            return type("Row", (), {"date": "2026-07-04"})()
        return type("Row", (), {})()

    def add(self, obj):
        return None

    def commit(self):
        return None

    def close(self):
        return None


class DummyVideo:
    def __init__(self, id):
        self.id = id


def _install_stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _prefect_decorator(*args, **kwargs):
    if args and callable(args[0]):
        return args[0]
    return lambda func: func


_install_stub_module("prefect", flow=lambda *args, **kwargs: (lambda func: func), task=_prefect_decorator)
_install_stub_module("prefect.logging", get_run_logger=lambda: DummyLogger())
_install_stub_module("dotenv", load_dotenv=lambda: None)

for module_name in [
    "tasks.event_research_agent.event_research_agent",
    "tasks.subtitle_file_generator.subtitle_gen",
    "tasks.upload_video.upload_video",
    "tasks.video_description_generator.video_description_generator",
    "tasks.video_generator.video_generator",
    "tasks.video_parts_generator.video_parts_generator",
    "tasks.video_script_generator.video_script_generator",
]:
    _install_stub_module(module_name, main=lambda *args, **kwargs: None)

from weekend_short_generation import flow
from weekend_short_generation import flow_init
from weekend_short_generation.tasks.upload_video_analytics import collect_video_analytics


def test_create_video_returns_new_video_id(monkeypatch):
    monkeypatch.setattr(flow, "get_db", lambda: iter([DummySession()]))
    monkeypatch.setattr(flow, "Video", lambda **kwargs: DummyVideo(id=99))
    monkeypatch.setattr(flow, "Towns", type("Towns", (), {"__name__": "Towns", "id": 1}))
    monkeypatch.setattr(flow, "Weekends", type("Weekends", (), {"__name__": "Weekends", "id": 1}))

    video_id = flow.create_video(weekend_id=1, town_id=2)

    assert video_id == 99


def test_main_flow_uses_expected_agent_sequence(monkeypatch):
    calls = []

    def fake_create_video(weekend_id, town_id):
        calls.append(("create_video", weekend_id, town_id))
        return 11

    def fake_agent(name):
        def _inner(*args, **kwargs):
            calls.append((name, kwargs.get("video_id") or kwargs.get("town_id")))
            return None

        return _inner

    monkeypatch.setattr(flow, "create_video", fake_create_video)
    monkeypatch.setattr(flow, "event_research_agent_main", fake_agent("event_research"))
    monkeypatch.setattr(flow, "video_script_generator_agent_main", fake_agent("video_script"))
    monkeypatch.setattr(flow, "video_parts_generator_agent_main", fake_agent("video_parts"))
    monkeypatch.setattr(flow, "video_generator_agent_main", fake_agent("video_generator"))
    monkeypatch.setattr(flow, "video_description_generator_agent_main", fake_agent("video_description"))
    monkeypatch.setattr(flow, "subtitle_gen_agent_main", fake_agent("subtitle"))
    monkeypatch.setattr(flow, "upload_video_main", fake_agent("upload"))
    monkeypatch.setattr(flow, "collect_video_analytics_main", fake_agent("analytics"))
    monkeypatch.setattr(flow, "get_run_logger", lambda: DummyLogger())
    monkeypatch.setattr(flow, "load_dotenv", lambda: None)

    flow.main_flow(weekend_id=1, town_id_list=[2, 3])

    assert calls[0] == ("create_video", 1, 2)
    assert any(call[0] == "event_research" for call in calls)
    assert any(call[0] == "upload" for call in calls)


def test_collect_video_analytics_updates_video_record(monkeypatch):
    class DummyClient:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def get_post_analytics(self, url):
            return {
                "url": url,
                "views": 123,
                "likes": 45,
                "comments": 6,
                "shares": 2,
                "watch_time_seconds": 987,
            }

    class DummySession:
        def __init__(self, video):
            self.video = video

        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.video

        def commit(self):
            return None

        def close(self):
            return None

    video = type(
        "VideoRecord",
        (),
        {
            "id": 17,
            "instagram_url": "https://instagram.com/p/123",
            "youtube_url": "https://youtube.com/watch?v=abc",
            "tiktok_url": "https://www.tiktok.com/@demo/video/123",
            "analytics_summary": "",
            "views_count": 0,
            "likes_count": 0,
            "comments_count": 0,
            "shares_count": 0,
            "watch_time_seconds": 0,
        },
    )()
    session = DummySession(video)

    monkeypatch.setattr(collect_video_analytics, "get_db", lambda: iter([session]))
    monkeypatch.setattr(collect_video_analytics, "UploadPostClient", DummyClient)

    collect_video_analytics.main(17)

    assert video.views_count == 123
    assert video.likes_count == 45
    assert video.comments_count == 6
    assert video.shares_count == 2
    assert video.watch_time_seconds == 987
    assert "instagram" in video.analytics_summary.lower()


def test_create_tables_recreates_schema(monkeypatch):
    created = {}

    class DummyEngine:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def _run_ddl_visitor(self, *args, **kwargs):
            return None

    def fake_create_engine(url, echo=False):
        created["url"] = url
        created["echo"] = echo
        return DummyEngine()

    monkeypatch.setattr(flow_init.os.path, "exists", lambda path: False)
    monkeypatch.setattr(flow_init.os, "remove", lambda path: None)
    monkeypatch.setattr(flow_init, "populate_towns", lambda: None)
    monkeypatch.setattr(flow_init, "populate_weekends", lambda: None)

    import sqlalchemy

    monkeypatch.setattr(sqlalchemy, "create_engine", fake_create_engine)
    monkeypatch.setattr(flow_init, "create_engine", fake_create_engine, raising=False)
    monkeypatch.setattr(flow_init, "Base", type("Base", (), {"metadata": type("Meta", (), {"create_all": staticmethod(lambda engine: None)})()}), raising=False)

    flow_init.create_tables()

    assert created["url"] == "sqlite:///data/local.db"
    assert created["echo"] is False
