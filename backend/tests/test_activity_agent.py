import os
import unittest
from unittest.mock import patch

from core.activities.agent import extract_activities_with_llm


class ActivityAgentTest(unittest.TestCase):
    def test_missing_llm_api_key_raises_configuration_error(self):
        snapshot = {
            "article": {"title": "线下沙龙报名", "description": "报名参加"},
            "content": {"text": "活动时间：本周六", "markdown": ""},
            "images": [],
        }

        with patch.dict(os.environ, {"LLM_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "LLM_API_KEY"):
                extract_activities_with_llm(snapshot)


if __name__ == "__main__":
    unittest.main()
