import unittest
from modules.ai_client import parse_json_response

class TestAIClient(unittest.TestCase):

    def test_parse_json_response_clean(self):
        raw = '{"key": "value", "items": [1, 2, 3]}'
        res = parse_json_response(raw)
        self.assertEqual(res, {"key": "value", "items": [1, 2, 3]})

    def test_parse_json_response_with_markdown_fences(self):
        raw = '```json\n{"html": "<p>Hello</p>", "events": []}\n```'
        res = parse_json_response(raw)
        self.assertEqual(res, {"html": "<p>Hello</p>", "events": []})

    def test_parse_json_response_with_surrounding_text(self):
        raw = 'Here is your response:\n{"result": "success"}\nHope this helps!'
        res = parse_json_response(raw)
        self.assertEqual(res, {"result": "success"})

if __name__ == "__main__":
    unittest.main()
