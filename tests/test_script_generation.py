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


_install_stub_module("prefect", task=lambda *args, **kwargs: (lambda func: func))
_install_stub_module("dotenv", load_dotenv=lambda: None)
_install_stub_module("research_agent", run_agent_sync=lambda *args, **kwargs: None)
_install_stub_module(
    "soundfile",
    write=lambda *args, **kwargs: None,
    info=lambda *args, **kwargs: types.SimpleNamespace(duration=1.0),
)
_install_stub_module("kokoro", KPipeline=lambda *args, **kwargs: None)
_install_stub_module(
    "langchain_core",
)
_install_stub_module(
    "langchain_core.prompts",
    PromptTemplate=type(
        "PromptTemplate", (), {"from_file": staticmethod(lambda *args, **kwargs: None)}
    ),
)
_install_stub_module("langchain_ollama", ChatOllama=type("ChatOllama", (), {}))

from tables import VideoSegmentsList, VideoSegmentsSchema
from weekend_short_generation.tasks.video_script_generator import video_script_generator


def test_check_text_spoken_length_matches_timestamps(monkeypatch):
    segments = VideoSegmentsList(
        segments=[
            VideoSegmentsSchema(
                script_text="This is a test script.",
                timestamp=0,
                scene_description=(
                    "This is a buxom test scene description that provides enough"
                    " context for the first segment so the validator treats it as"
                    " sufficiently detailed."
                ),
                event_id=-1,
                caption="This is a caption for the first segment.",
            )
        ]
    )

    monkeypatch.setattr(
        video_script_generator,
        "generate_audio_file",
        lambda text, file_path="your_audio_file.wav": 6.0,
    )

    res = video_script_generator.check_text_spoken_length_matches_timestamps(segments)

    assert res == "success"


def test_check_text_spoken_length_matches_timestamps_accepts_list_of_dicts(
    monkeypatch,
):
    segments = [
        {
            "script_text": "This is a test script.",
            "timestamp": 0,
            "scene_description": (
                "This is a buxom test scene description that provides enough"
                " context for the first segment so the validator treats it as"
                " sufficiently detailed."
            ),
            "event_id": -1,
            "caption": "This is a caption for the first segment.",
        }
    ]

    monkeypatch.setattr(
        video_script_generator,
        "generate_audio_file",
        lambda text, file_path="your_audio_file.wav": 6.0,
    )

    res = video_script_generator.check_text_spoken_length_matches_timestamps(segments)

    assert res == "success"


def test_check_text_spoken_length_matches_timestamps_reports_timing_mismatch(
    monkeypatch,
):

    segments = VideoSegmentsList(
        segments=[
            VideoSegmentsSchema(
                script_text="This is a test script.",
                timestamp=0,
                scene_description=(
                    "This is a buxom test scene description that provides enough"
                    " context for the first segment so the validator treats it as"
                    " sufficiently detailed."
                ),
                event_id=0,
                caption="This is a caption for the first segment.",
            ),
            VideoSegmentsSchema(
                script_text=(
                    "This is another test script that is significantly longer than the"
                    " previous one."
                ),
                timestamp=4,
                scene_description=(
                    "This is another buxom test scene description that provides enough"
                    " context for the second segment so the validator treats it as"
                    " sufficiently detailed."
                ),
                event_id=1,
                caption="This is a caption for the second segment.",
            ),
        ]
    )

    monkeypatch.setattr(
        video_script_generator,
        "generate_audio_file",
        lambda text, file_path="your_audio_file.wav": 5.0,
    )

    res = video_script_generator.check_text_spoken_length_matches_timestamps(segments)

    assert "script takes approximately" in res


def test_check_text_spoken_length_matches_timestamps_reports_short_scene_description(
    monkeypatch,
):
    segments = VideoSegmentsList(
        segments=[
            VideoSegmentsSchema(
                script_text="This is a test script.",
                timestamp=0,
                scene_description="Too short.",
                event_id=-1,
                caption="This is a caption for the first segment.",
            )
        ]
    )

    monkeypatch.setattr(
        video_script_generator,
        "generate_audio_file",
        lambda text, file_path="your_audio_file.wav": 5.0,
    )

    res = video_script_generator.check_text_spoken_length_matches_timestamps(segments)

    assert "scene description" in res and "too short" in res


def test_check_script_rejects_zero_segment_scripts():
    from video_story_generation.tasks.generate_script import generate_script as gs

    result = gs.check_script({"video_segments": [], "people_and_props": []})

    assert "zero video segments" in result.lower()
    assert "exactly" in result.lower()


def test_generate_script_retries_when_first_draft_has_zero_segments(monkeypatch):
    from video_story_generation.tasks.generate_script import generate_script as gs

    class _PromptTemplateStub:
        @staticmethod
        def from_file(_path):
            class _T:
                @staticmethod
                def format(**_kwargs):
                    return "stub prompt"

            return _T()

    class _StructuredModelStub:
        def __init__(self):
            self.call_count = 0

        def invoke(self, _messages):
            self.call_count += 1
            if self.call_count == 1:
                return {
                    "video_segments": [],
                    "people_and_props": [
                        {
                            "name": "Hero",
                            "prompt": " ".join(["word"] * 45),
                        }
                    ],
                }

            segments = []
            for idx in range(gs.TARGET_SEGMENT_COUNT):
                segments.append(
                    {
                        "start_image_prompt": " ".join(["image"] * 45),
                        "video_prompt": " ".join(["motion"] * 25),
                        "start_image_people_and_props_names": "Hero",
                        "narrator_script": " ".join(["narration"] * 10),
                        "timestamp": idx * gs.SEGMENT_LENGTH,
                    }
                )

            return {
                "video_segments": segments,
                "people_and_props": [
                    {
                        "name": "Hero",
                        "prompt": " ".join(["word"] * 45),
                    }
                ],
            }

    structured_stub = _StructuredModelStub()

    class _ModelStub:
        def with_structured_output(self, _schema_type, method="json_schema"):
            assert method == "json_schema"
            return structured_stub

    monkeypatch.setattr(gs, "PromptTemplate", _PromptTemplateStub)
    monkeypatch.setattr(gs, "_script_generation_model", lambda: _ModelStub())

    # Avoid hitting expensive validators; this test targets generation retry behavior.
    monkeypatch.setattr(gs, "check_script", lambda _payload: "success")

    result = gs._generate_script_until_valid(
        user_prompt_params={},
        system_prompt_params={},
        prompt_dir=Path("."),
    )

    assert structured_stub.call_count == 2
    assert len(result.video_segments) == gs.TARGET_SEGMENT_COUNT
