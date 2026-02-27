import os
import unittest

from dotenv import load_dotenv
from openai import OpenAI


@unittest.skipUnless(
    (os.getenv("OPENAI_LIVE_TEST") == "1") and bool(os.getenv("OPENAI_API_KEY")),
    "Set OPENAI_LIVE_TEST=1 and OPENAI_API_KEY to run live integration test.",
)
class TestAgentLive(unittest.TestCase):
    def test_live_chat_completion(self) -> None:
        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are CAD Guardian assistant."},
                {"role": "user", "content": "Say: Infrastructure layer is operational."},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        self.assertTrue(content)


if __name__ == "__main__":
    unittest.main()
