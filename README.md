# tts-stt

Lightweight text-to-speech and speech-to-text CLI utilities. `speak.py` wraps ElevenLabs for natural voice synthesis; `listen.py` wraps local Whisper for transcription. Designed as plug-and-play helpers other tools can shell out to.

## Scripts

| Script | Purpose |
|--------|---------|
| `speak.py` | Text → ElevenLabs → mp3 file. Prints output path to stdout. |
| `listen.py` | Audio file → Whisper → transcript. Prints text to stdout. |
| `voice_play.py` | Generate + play speech in one shot. |
| `list_voices.py` | List available ElevenLabs voices for the account. |

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # then fill in ELEVENLABS_API_KEY
```

STT requires the `whisper` CLI on `PATH`:
- Mac: `brew install openai-whisper`
- Linux: `pip3 install openai-whisper`

## Usage

```bash
python speak.py "Hello there"
python speak.py "Some text" --voice <voice_id>

python listen.py /path/to/audio.ogg
```

## Configuration

All settings live in `.env` (see `env.example` for the full list). Per-instance voice config is the main knob — MacClaude uses Scott (Scottish), Fraggy uses Chris (American), Claudsson uses a Mandarin voice. Each bot sets its own `TTS_VOICE_ID`, `TTS_ACCENT_TAG`, and `STT_LANGUAGE` via its own `.env`.

Key env vars:
- `ELEVENLABS_API_KEY` — required for TTS
- `TTS_VOICE_ID`, `TTS_MODEL`, `TTS_ACCENT_TAG`, `TTS_SPEED` — voice tuning
- `STT_MODEL`, `STT_LANGUAGE`, `STT_OUTPUT_DIR` — whisper tuning

## Output

- TTS mp3s land in `output/` (gitignored)
- Whisper intermediates land in `transcripts/` (gitignored, cleaned up per run)
