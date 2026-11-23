"""Tests for the pure logic (no Windows, GUI, microphone or Ollama needed).  Run: pytest"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PIL import Image

import locator
from textutil import clean_for_speech, clean_transcript, split_sentences, wants_pointer


def test_split_sentences_keeps_remainder():
    done, rest = split_sentences("Click File. Then choose Save. Next, wait")
    assert done == ["Click File.", "Then choose Save."]
    assert rest == "Next, wait"


def test_clean_helpers():
    assert clean_for_speech("**Click** the `Save` button") == "Click the Save button"
    assert clean_transcript("[BLANK_AUDIO] where is   the (music) save button") == "where is the save button"


def test_parse_cell():
    assert locator.parse_cell('{"cell": 42}', 96) == 42
    assert locator.parse_cell('{"cell": 0}', 96) == 0
    assert locator.parse_cell("I think it's cell 17.", 96) == 17
    assert locator.parse_cell('{"cell": 500}', 96) is None
    assert locator.parse_cell("no idea", 96) is None


class FakeLLM:
    def __init__(self, answers):
        self.answers = list(answers)

    def ask_images(self, prompt, images, max_tokens=30):
        return self.answers.pop(0)


def test_locate_top_right_stays_top_right():
    img = Image.new("RGB", (1920, 1080))
    fx, fy = locator.locate(FakeLLM(['{"cell": 3}'] * 3), img, "where is close")
    assert fx > 0.95 and fy < 0.05


def test_locate_bottom_right_is_not_top_right():
    img = Image.new("RGB", (1920, 1080))
    fx, fy = locator.locate(FakeLLM(['{"cell": 9}'] * 3), img, "where is send")
    assert fx > 0.95 and fy > 0.95


def test_locate_centre_cell_is_screen_centre():
    img = Image.new("RGB", (1920, 1080))
    fx, fy = locator.locate(FakeLLM(['{"cell": 5}'] * 3), img, "x")
    assert abs(fx - 0.5) < 0.01 and abs(fy - 0.5) < 0.01


def test_locate_returns_none_for_conceptual_question():
    img = Image.new("RGB", (1920, 1080))
    llm = FakeLLM(['{"cell": 0}'])
    assert locator.locate(llm, img, "what is a variable") is None
    assert llm.answers == []          # it stopped after one call


def test_locate_keeps_best_guess_when_a_later_round_fails():
    img = Image.new("RGB", (1920, 1080))
    fx, fy = locator.locate(FakeLLM(['{"cell": 3}', "garbage", "garbage"]), img, "x")
    assert abs(fx - 5 / 6) < 1e-6 and abs(fy - 1 / 6) < 1e-6


def test_locate_must_find_retries_instead_of_giving_up():
    img = Image.new("RGB", (1920, 1080))
    llm = FakeLLM(['{"cell": 0}', '{"cell": 3}', '{"cell": 3}', '{"cell": 3}'])
    fx, fy = locator.locate(llm, img, "where is save", allow_none=False)
    assert fx > 0.95 and fy < 0.05


def test_locate_must_find_gives_up_after_two_tries():
    img = Image.new("RGB", (1920, 1080))
    assert locator.locate(FakeLLM(["no", "no"]), img, "x", allow_none=False) is None


def test_wants_pointer():
    assert wants_pointer("Where should I click to save?")
    assert wants_pointer("how do I open settings")
    assert wants_pointer("which button exports the file")
    assert not wants_pointer("explain what a variable is")



# ---------------------------------------------------------------- Gemini + provider switching
import json
from unittest import mock

import gemini_client
from gemini_client import GeminiClient, parse_target, to_gemini_contents


def test_parse_target_box_centre():
    # box [ymin, xmin, ymax, xmax] -> centre (x=0.5, y=0.2)
    fx, fy = parse_target('{"box_2d": [100, 400, 300, 600], "label": "Settings"}')
    assert abs(fx - 0.5) < 1e-9 and abs(fy - 0.2) < 1e-9


def test_parse_target_top_right_is_top_right():
    fx, fy = parse_target('{"box_2d": [10, 950, 50, 990]}')
    assert fx > 0.95 and fy < 0.05


def test_parse_target_handles_fences_lists_and_points():
    assert parse_target('```json\n[{"box_2d": [0, 0, 100, 100]}]\n```') == (0.05, 0.05)
    assert parse_target('{"point": [500, 250]}') == (0.25, 0.5)      # point is [y, x]
    assert parse_target("it is around 100, 400, 300, 600") == (0.5, 0.2)


def test_parse_target_none_cases():
    assert parse_target('{"box_2d": null}') is None
    assert parse_target("I cannot find it") is None
    assert parse_target('{"box_2d": [1, 2, 3, 5000]}') is None
    assert parse_target("") is None


def test_to_gemini_contents_maps_roles_and_images():
    system, contents = to_gemini_contents([
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "look", "images": ["QUJD"]},
    ])
    assert system == "be brief"
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[2]["parts"][1]["inline_data"] == {"mime_type": "image/jpeg", "data": "QUJD"}


class FakeGemini:
    native_pointing = True
    name = "gemini"

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def point(self, image, query, allow_none=True):
        self.calls += 1
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_native_locator_uses_point_not_grid():
    img = Image.new("RGB", (1920, 1080))
    llm = FakeGemini([(0.9, 0.1)])
    assert locator.locate(llm, img, "where is close") == (0.9, 0.1)
    assert llm.calls == 1


def test_native_locator_none_is_allowed_for_conceptual_questions():
    img = Image.new("RGB", (1920, 1080))
    llm = FakeGemini([None])
    assert locator.locate(llm, img, "what is a variable", allow_none=True) is None
    assert llm.calls == 1


def test_native_locator_retries_once_when_target_must_exist():
    img = Image.new("RGB", (1920, 1080))
    llm = FakeGemini([RuntimeError("boom"), (0.2, 0.3)])
    assert locator.locate(llm, img, "where is save", allow_none=False) == (0.2, 0.3)
    assert llm.calls == 2


def test_gemini_check_without_key():
    problems = GeminiClient(api_key="").check()
    assert problems and "GEMINI_API_KEY" in problems[0]


def test_gemini_stream_chat_parses_sse():
    class Resp:
        status_code = 200

        def iter_lines(self):
            chunks = [
                {"candidates": [{"content": {"parts": [{"text": "Click "}]}}]},
                {"candidates": [{"content": {"parts": [{"text": "Settings.", "thought": False}]}}]},
                {"candidates": [{"content": {"parts": [{"text": "(hidden)", "thought": True}]}}]},
            ]
            yield b""
            for c in chunks:
                yield b"data: " + json.dumps(c).encode()

    with mock.patch.object(gemini_client.requests, "post", return_value=Resp()) as post:
        client = GeminiClient(api_key="k", model="gemini-2.5-flash")
        out = "".join(client.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == "Click Settings."
    body = post.call_args.kwargs["json"]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "k"


def test_gemini_point_end_to_end_with_fake_http():
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            text = '{"box_2d": [20, 900, 60, 980], "label": "Close"}'
            return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    with mock.patch.object(gemini_client.requests, "post", return_value=Resp()):
        fx, fy = GeminiClient(api_key="k").point(Image.new("RGB", (800, 600)), "where is close")
    assert fx > 0.9 and fy < 0.1


def test_gemini_quota_error_is_friendly():
    class Resp:
        status_code = 429
        text = "quota"

        @staticmethod
        def json():
            return {"error": {"message": "Resource exhausted"}}

    try:
        gemini_client._check(Resp())
    except RuntimeError as exc:
        assert "quota" in str(exc).lower() and "Ollama" in str(exc)
    else:
        raise AssertionError("expected an error")


def test_make_client_picks_provider():
    import providers
    assert providers.make_client("gemini").name == "gemini"
    assert providers.make_client("ollama").name == "ollama"
    assert providers.make_client("ollama").native_pointing is False
