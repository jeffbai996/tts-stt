# tts-stt: `listen.py` — batch STT via local whisper

**Date:** 2026-04-16
**Status:** Design drafted, awaiting user review before implementation
**Scope:** Single script addition to the tts-stt repo. No changes to `speak.py`, `voice_play.py`, or `list_voices.py`.

## Context

The tts-stt repo currently ships two capabilities: text-to-speech (`speak.py`, ElevenLabs) and Discord voice-channel playback (`voice_play.py`). The repo name promises a third — speech-to-text — which has never been implemented. Voice notes currently arrive in each bot's Discord inbox (`~/.claude/channels/discord/inbox/`) as Ogg Opus files and are not processed.

The `whisper` CLI (from `openai-whisper`) is already installed on both deployment targets (Mac via homebrew, fragserv WSL via pip3). Benchmarking on Apple Silicon (Mac, base model) showed 0.76x real-time transcription of real speech — a 7-second clip transcribed in 5.4 seconds with perfect accuracy. fragserv x86 CPU is expected to run ~1.5–2x real-time, acceptable for async voice-note handling.

This spec adds batch STT only. Streaming STT for real-time Discord voice chat is a separate project (see fragserv-side `project_voice_chat.md`) and is out of scope.

## Goals

1. **Mirror `speak.py`'s contract.** File path in, pure stdout output, env-driven config, zero bot-specific knowledge.
2. **Plug-and-play across bots.** Same script runs MacClaude (Mac, English, Scott voice) and would run Fraggy / Claudsson (fragserv, potentially different languages) with no code changes — only `.env` differences.
3. **No new Python dependencies.** The `whisper` CLI is a system tool, not a pip dep. Adding `openai-whisper` to `requirements.txt` would drag ~2GB of PyTorch into every venv.
4. **Test-driven.** Test plan reviewed and approved before implementation per CLAUDE.md policy.

## Non-goals

- Recording audio from mic or Discord voice channels (separate concern, pulls in `fraggy-voice` scope).
- Streaming transcription (requires Deepgram / OpenAI Realtime — separate project).
- Language auto-detection by default (env default is `en` for latency; overridable per-bot).
- Wiring STT directly into the Discord plugin source (hot-reload constraints documented in `project_voice_chat.md`; bots invoke `listen.py` as a subprocess from their normal response flow instead).

## Architecture

Single script at `listen.py`, sibling to `speak.py`. Subprocesses to the `whisper` CLI binary. Loads config via `python-dotenv`, identical to `speak.py`'s pattern.

```
tts-stt/
├── speak.py          # existing, untouched
├── voice_play.py     # existing, untouched
├── list_voices.py    # existing, untouched
├── listen.py         # NEW
├── tests/
│   └── test_listen.py  # NEW
├── transcripts/      # NEW runtime directory (gitignored, like output/)
├── requirements.txt  # unchanged (whisper is a system tool, not a pip dep)
└── .env.example      # UPDATED with STT_* knobs
```

## Interface

### CLI

```bash
python listen.py /path/to/voice_note.ogg
# → prints transcribed text to stdout, newline-terminated.
```

Optional flags, matching `speak.py`'s style:

```bash
python listen.py audio.ogg --model small      # override STT_MODEL
python listen.py audio.ogg --language zh      # override STT_LANGUAGE
```

### Stdout contract

**Pure transcript.** No logs, no banners, no JSON wrapper. Callers capture it cleanly:

```python
transcript = subprocess.run(
    ["python", "listen.py", path],
    capture_output=True, check=True,
).stdout.decode().strip()
```

### Stderr contract

All diagnostic output (whisper's progress, errors, warnings) goes to stderr. Exit code 0 on success, non-zero on any failure.

### Python API

```python
from listen import transcribe
text = transcribe("/path/to/audio.ogg", model="base", language="en")
```

Returns the stripped transcript string. Raises `RuntimeError` on any failure with a descriptive message.

## Environment Configuration

New entries in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `STT_MODEL` | `base` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `STT_LANGUAGE` | `en` | ISO language code; skips whisper's auto-detect for latency |
| `STT_OUTPUT_DIR` | `<script_dir>/transcripts/` | Where whisper writes intermediate files (script cleans up). Resolves relative to `listen.py` itself, mirroring `speak.py`'s `OUTPUT_DIR` pattern. |

No new secrets. `ELEVENLABS_API_KEY` stays a TTS-only concern.

### `.env.example` additions

```bash
# ─── STT (speech-to-text) ───────────────────────────────
# Requires `whisper` CLI on PATH.
# Install: brew install openai-whisper (Mac) or pip3 install openai-whisper (Linux)

# Model size — trade speed vs accuracy. base is 0.76x real-time on Apple Silicon.
STT_MODEL=base

# Language code (e.g. en, zh, ja). Skips auto-detect. Set per bot:
#   MacClaude:  en
#   Claudsson:  zh
#   Fraggy:     en
STT_LANGUAGE=en

# Where intermediate whisper files land. Gitignored; cleaned up after each run.
STT_OUTPUT_DIR=./transcripts/
```

## Error Handling

Follows `speak.py`'s pattern — raise `RuntimeError` with context, let the caller decide what to do.

| Failure | Behavior |
|---|---|
| Input file doesn't exist | `RuntimeError("file not found: <path>")`, exit 1 |
| `whisper` CLI not on PATH | `RuntimeError("whisper CLI not found. Install: brew install openai-whisper")`, exit 1 |
| Whisper subprocess non-zero exit | `RuntimeError(f"whisper failed: {stderr}")`, exit 1 |
| Empty transcription (silent audio) | Return empty string `""`, exit 0 — not an error; callers decide |
| Malformed audio (whisper handles) | Whisper's own error → caught and re-raised as `RuntimeError` |

## Implementation Details

1. **Locate `whisper` binary** via `shutil.which("whisper")`. Fail fast if absent — no fallback to Python package import (keeps the system-tool contract explicit).
2. **Invoke whisper** with `subprocess.run()`:
   ```
   whisper <audio_path> \
     --model <STT_MODEL> \
     --language <STT_LANGUAGE> \
     --output_dir <STT_OUTPUT_DIR> \
     --output_format txt \
     --fp16 False \
     --verbose False
   ```
   `--fp16 False` required on CPU-only machines (both Mac CPU and fragserv WSL). `--verbose False` keeps whisper's per-segment chatter out of stderr.
3. **Read transcript** from the `.txt` file whisper writes into `STT_OUTPUT_DIR`. Strip surrounding whitespace.
4. **Clean up** the intermediate `.txt` (and `.json`, `.srt`, etc. if whisper leaves any) before exit. Mirrors `speak.py`'s ffmpeg temp-file hygiene.
5. **Print transcript to stdout**, newline-terminated, nothing else.

## Testing Plan

Test file: `tests/test_listen.py`, pytest. Requires approval before implementation per CLAUDE.md.

Fast tests (mocked, <0.1s each):

| Test | What it verifies |
|---|---|
| `test_missing_file_raises` | Non-existent path → `RuntimeError` with "file not found" |
| `test_whisper_not_found_raises` | `shutil.which` returns None → `RuntimeError` with install hint |
| `test_whisper_subprocess_failure_raises` | Mocked subprocess non-zero exit → `RuntimeError` with whisper stderr |
| `test_whisper_produced_no_output_raises` | Subprocess exits 0 but no `.txt` file written → `RuntimeError` with clear message (not raw FileNotFoundError) |
| `test_empty_audio_returns_empty_string` | Whisper writes empty txt → function returns `""` (not an exception) |
| `test_stt_model_env_override` | `STT_MODEL=small` in monkeypatched env → subprocess called with `--model small` |
| `test_stt_language_env_override` | `STT_LANGUAGE=zh` in env → subprocess called with `--language zh` |
| `test_language_kwarg_overrides_env` | `STT_LANGUAGE=en` env + `language="zh"` kwarg → subprocess sees `zh` (library-level override) |
| `test_cli_error_path_exits_nonzero_with_stderr` | Real subprocess CLI: nonexistent file → `ERROR:` on stderr, empty stdout, exit 1 (verifies argparse wiring end-to-end) |
| `test_cleanup_removes_intermediate_files` | After success, `STT_OUTPUT_DIR` has no `.txt`/`.json`/`.srt` leftovers |
| `test_cleanup_on_whisper_failure` | Whisper fails → any partial output files still cleaned up (no accumulating garbage) |
| `test_default_output_dir_is_script_relative` | With `STT_OUTPUT_DIR` unset, script uses `<script_dir>/transcripts/`, not CWD-relative — verifies the plug-and-play portability guarantee |

Slow test (real whisper invocation, ~5s, marked `@pytest.mark.slow`):

| Test | What it verifies |
|---|---|
| `test_transcribes_real_speech` | Uses macOS `say` (Mac) or a checked-in `tests/fixtures/hello.wav` (portable) → asserts transcript contains expected words like "hello" or "test" |

`@pytest.mark.slow` tests can be skipped via `pytest -m "not slow"` in CI or locally when iterating.

## Plug-and-Play Portability

This is the load-bearing section — the "multi-bot OSS foundation" framing requires that a new bot (say, Bot #4) can clone tts-stt and run `listen.py` with zero Python changes.

Guarantees:

1. **No hardcoded paths.** `STT_OUTPUT_DIR` resolves relative to the script's own directory by default.
2. **No hardcoded bot identity.** Script has no knowledge of MacClaude, Fraggy, Claudsson, or any bot name.
3. **No hardcoded language or model.** Both live in `.env`, overridable per-bot.
4. **System-level dep only.** `whisper` CLI on PATH. Documented in `.env.example` (README creation deferred). No PyTorch in the venv.
5. **Deploy pattern unchanged.** `git pull` on Mac, `git pull` on fragserv. No schema migration, no new ports, no new services.

## README Updates

The repo has no README currently. This spec does not require creating one — repo hardening (README, tests for existing code, cleanup of the empty `repos/macclaude-tts/` subdir, v0.1 tag) is a separate follow-up task, not part of this work. The `.env.example` additions document the STT knobs sufficiently for now.

## Migration / Rollout

No migration needed. `listen.py` is purely additive. Existing `speak.py` and `voice_play.py` callers are unaffected.

Rollout order once implementation is complete:
1. Ship on Mac (MacClaude): `git push` → `git pull` on Mac → test with a Discord voice note in MacClaude's inbox
2. Ship on fragserv (Fraggy / Claudsson): `git pull` on fragserv → test with a voice note in Fraggy's inbox
3. Update fragserv-side `project_voice_chat.md` memory to note batch STT is now live (streaming voice chat remains a separate TBD).

## Open Questions

None — all resolved during brainstorming:
- ✅ Hosted API vs local CLI → local CLI (whisper on PATH)
- ✅ Model choice → `base` default, env-overridable
- ✅ URL input vs file path → file path only (Discord plugin already downloads attachments)
- ✅ Batch vs streaming → batch only in this spec; streaming is a separate project
- ✅ Central service vs per-machine → per-machine (bots run on different hosts)
- ✅ Recording vs playback-only → playback-only; recording is out of scope

## Approval Gate

Next step: user reviews this spec, then one of:
- **Approve** → invoke `writing-plans` skill to produce the ordered implementation checklist
- **Revise** → edit this doc inline and re-review
