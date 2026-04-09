"""List ElevenLabs voices, optionally filtered by keyword (e.g. 'scottish')."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ELEVENLABS_API_KEY")


def list_voices(filter_keyword: str = "") -> None:
    resp = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": API_KEY},
    )
    resp.raise_for_status()
    voices = resp.json()["voices"]

    for v in voices:
        name = v["name"]
        voice_id = v["voice_id"]
        labels = v.get("labels", {})
        accent = labels.get("accent", "")
        description = labels.get("description", "")
        category = v.get("category", "")

        if filter_keyword:
            searchable = f"{name} {accent} {description} {category}".lower()
            if filter_keyword.lower() not in searchable:
                continue

        print(f"{name:<30} {voice_id}  accent={accent}  {description}")


if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    list_voices(keyword)
