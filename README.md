# tts-stt

Lightweight text-to-speech and speech-to-text CLI utilities. `speak.py` wraps ElevenLabs for natural voice synthesis; `listen.py` wraps local Whisper for transcription. Designed as plug-and-play helpers other tools can shell out to.

## Scripts

| Script | Purpose |
|--------|---------|
| `speak.py` | Text → ElevenLabs → mp3 file. Prints output path to stdout. |
| `listen.py` | Audio file → Whisper → transcript. Prints text to stdout. |
| `voice_play.py` | Generate + play speech in one shot. |
| `list_voices.py` | List available ElevenLabs voices for the account. |
| `voice_mode.py` | Discord voice-mode routing — pairs a text channel with a voice channel, checks whether an allowlisted human is present, and plays TTS audio there. See below. |

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

All settings live in `.env` (see `env.example` for the full list). Per-instance voice config is the main knob — give each agent/bot its own voice by setting `TTS_VOICE_ID`, `TTS_ACCENT_TAG`, and `STT_LANGUAGE` in that instance's `.env`.

Key env vars:
- `ELEVENLABS_API_KEY` — required for TTS
- `TTS_VOICE_ID`, `TTS_MODEL`, `TTS_ACCENT_TAG`, `TTS_SPEED` — voice tuning
- `STT_MODEL`, `STT_LANGUAGE`, `STT_OUTPUT_DIR` — whisper tuning

## Output

- TTS mp3s land in `output/` (gitignored)
- Whisper intermediates land in `transcripts/` (gitignored, cleaned up per run)

## Voice-mode routing

`voice_mode.py` lets a text-only Discord bot speak into a paired voice channel — pair a text channel with a voice channel, gate on an allowlisted human actually being present, then play or synthesize audio there.

```bash
python voice_mode.py channels                        # list guilds + voice channels
python voice_mode.py check <text_channel_id>          # is voice mode active for this text channel?
python voice_mode.py play <text_channel_id> <mp3>     # verify presence + join paired VC + play + leave
python voice_mode.py say <text_channel_id> "text"     # streaming TTS piped straight to the VC, no mp3 file
```

`check`/`play` print a single JSON object on stdout. `play` and `say` re-verify the allowlisted user is present in the same gateway session right before joining, so a stale `check` can't make the bot barge into an empty channel.

Config is a local, gitignored JSON file (`VOICE_MODE_CONFIG` env var, defaults to `voice_mode.json` next to the script):

```json
{
  "allow_user_ids": ["123456789012345678"],
  "pairs": { "<text_channel_id>": "<voice_channel_id>" }
}
```

Requires `DISCORD_BOT_TOKEN` in `.env`.
