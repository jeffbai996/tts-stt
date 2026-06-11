"""
Voice-mode routing for a Discord bot: pair text channels with voice channels,
detect whether an allowlisted human is sitting in the paired voice channel,
and play TTS audio there.

The pairing/allowlist config lives in a local JSON file (gitignored — it
contains server-specific channel and user IDs):

    {
      "allow_user_ids": ["123456789012345678"],
      "pairs": { "<text_channel_id>": "<voice_channel_id>" }
    }

Usage:
    python voice_mode.py channels                       # list guilds + voice channels
    python voice_mode.py check <text_channel_id>        # is voice mode active for this text channel?
    python voice_mode.py play <text_channel_id> <mp3>   # verify + join paired VC + play + leave

`check` and `play` print a single JSON object on stdout. `play` re-verifies
presence in the same gateway session before joining, so a stale `check` can't
make the bot barge into an empty channel.

Environment (via .env):
    DISCORD_BOT_TOKEN — bot token
    VOICE_MODE_CONFIG — optional path to config JSON (default: voice_mode.json next to this file)
"""
import os
import sys
import json
import asyncio
import argparse
import logging
from dataclasses import dataclass

import discord
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "voice_mode.json")


def resolve_config_path() -> str:
    """Pick the config for THIS bot instance.

    Several bots can share this repo checkout; each must land on its own
    config or one bot ends up speaking through another's pairing. Order:
    explicit VOICE_MODE_CONFIG > the running agent's CLAUDE_CONFIG_DIR
    (set per bot instance) > the repo-local default.
    """
    explicit = os.getenv("VOICE_MODE_CONFIG")
    if explicit:
        return explicit
    agent_dir = os.getenv("CLAUDE_CONFIG_DIR")
    if agent_dir:
        candidate = os.path.join(agent_dir, "voice_mode.json")
        if os.path.exists(candidate):
            return candidate
    return DEFAULT_CONFIG_PATH
# Hard ceiling on gateway connect + action so callers never hang on a bad network
TIMEOUT_S = float(os.getenv("VOICE_MODE_TIMEOUT_S", "30"))

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceModeConfig:
    allow_user_ids: frozenset
    pairs: dict  # text_channel_id (int) -> voice_channel_id (int)
    token_file: str = None  # optional env-format file holding DISCORD_BOT_TOKEN
    enabled: bool = True  # master switch — lets an external controller force text mode

    @classmethod
    def load(cls, path: str = None) -> "VoiceModeConfig":
        path = path or resolve_config_path()
        with open(path) as f:
            data = json.load(f)
        if "allow_user_ids" not in data:
            raise ValueError(f"config {path} missing 'allow_user_ids'")
        if "pairs" not in data:
            raise ValueError(f"config {path} missing 'pairs'")
        return cls(
            allow_user_ids=frozenset(int(u) for u in data["allow_user_ids"]),
            pairs={int(k): int(v) for k, v in data["pairs"].items()},
            token_file=data.get("token_file"),
            enabled=bool(data.get("enabled", True)),
        )

    def paired_vc(self, text_channel_id: int):
        return self.pairs.get(int(text_channel_id))


def allowlisted_present(present_ids: set, allow_ids) -> bool:
    """True if any allowlisted user is among the IDs present in the voice channel."""
    return bool(set(present_ids) & set(allow_ids))


def _present_ids(vc: discord.VoiceChannel) -> set:
    # voice_states works without the privileged members intent, unlike .members
    return set(vc.voice_states.keys())


def _emit(result: dict) -> None:
    print(json.dumps(result))


async def _with_client(action) -> dict:
    """Connect a throwaway gateway session, run action(client), return its dict."""
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    client = discord.Client(intents=intents)
    result: dict = {}
    done = asyncio.Event()

    @client.event
    async def on_ready():
        nonlocal result
        try:
            result = await action(client)
        except Exception as e:  # surface as JSON, not a stack trace
            result = {"ok": False, "error": str(e)}
        finally:
            done.set()

    async with client:
        gateway = asyncio.create_task(client.start(BOT_TOKEN))
        try:
            await asyncio.wait_for(done.wait(), timeout=TIMEOUT_S)
        except asyncio.TimeoutError:
            result = {"ok": False, "error": f"timed out after {TIMEOUT_S}s"}
        finally:
            gateway.cancel()
    return result


def _resolve_vc(client: discord.Client, cfg: VoiceModeConfig, text_channel_id: int):
    """Return (vc, error_dict). Exactly one is None."""
    vc_id = cfg.paired_vc(text_channel_id)
    if vc_id is None:
        return None, {"ok": True, "active": False, "reason": "text channel not paired"}
    vc = client.get_channel(vc_id)
    if not isinstance(vc, discord.VoiceChannel):
        return None, {"ok": False, "error": f"voice channel {vc_id} not found or not a voice channel"}
    return vc, None


async def cmd_channels(client: discord.Client) -> dict:
    guilds = []
    for g in client.guilds:
        guilds.append({
            "guild": g.name,
            "guild_id": str(g.id),
            "voice_channels": [{"name": c.name, "id": str(c.id)} for c in g.voice_channels],
        })
    return {"ok": True, "guilds": guilds}


def make_check(cfg: VoiceModeConfig, text_channel_id: int):
    async def check(client: discord.Client) -> dict:
        vc, err = _resolve_vc(client, cfg, text_channel_id)
        if err:
            return err
        present = _present_ids(vc)
        active = allowlisted_present(present, cfg.allow_user_ids)
        return {
            "ok": True,
            "active": active,
            "vc_id": str(vc.id),
            "vc_name": vc.name,
            "present": [str(i) for i in present],
        }
    return check


def make_play(cfg: VoiceModeConfig, text_channel_id: int, mp3_path: str):
    async def play(client: discord.Client) -> dict:
        vc, err = _resolve_vc(client, cfg, text_channel_id)
        if err:
            return err
        if not allowlisted_present(_present_ids(vc), cfg.allow_user_ids):
            return {"ok": True, "played": False, "reason": "no allowlisted user in voice channel"}
        voice = await vc.connect()
        try:
            voice.play(discord.FFmpegPCMAudio(mp3_path))
            while voice.is_playing():
                await asyncio.sleep(0.5)
        finally:
            await voice.disconnect()
        return {"ok": True, "played": True, "vc_id": str(vc.id), "vc_name": vc.name}
    return play


def vc_tts_request(text: str, voice_id: str, api_key: str) -> tuple:
    """Build (url, headers, payload) for the streaming VC synthesis request.

    Pure so it's testable. VC speech trades polish for snappiness: Flash model
    (~75ms time-to-first-byte vs seconds on v3) and native `speed` in
    voice_settings instead of a post-hoc ffmpeg atempo pass (a stream can't be
    atempo'd after the fact anyway).
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": os.getenv("TTS_MODEL_VC", "eleven_flash_v2_5"),
        "voice_settings": {
            "stability": float(os.getenv("TTS_STABILITY", "0.35")),
            "similarity_boost": float(os.getenv("TTS_SIMILARITY", "0.85")),
            "style": float(os.getenv("TTS_STYLE", "0.60")),
            "use_speaker_boost": True,
            "speed": float(os.getenv("TTS_SPEED", "1.05")),
        },
    }
    return url, headers, payload


def _start_tts_stream(text: str, voice_id: str, write_fd: int) -> "threading.Thread":
    """Stream ElevenLabs audio chunks into a pipe from a worker thread.

    The read end feeds ffmpeg, so playback starts on the first chunk while the
    tail is still synthesising. Errors surface as a closed pipe; the caller
    treats zero-byte audio as failure.
    """
    import threading
    import requests

    url, headers, payload = vc_tts_request(text, voice_id, os.getenv("ELEVENLABS_API_KEY", ""))

    def pump() -> None:
        try:
            with requests.post(url, headers=headers, json=payload, stream=True, timeout=30) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        os.write(write_fd, chunk)
        except Exception as e:
            log.warning("tts stream failed: %s", e)
        finally:
            os.close(write_fd)

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    return t


def make_say(cfg: VoiceModeConfig, text_channel_id: int, text: str, voice_id: str):
    """One-shot speak: presence gate, then TTS-stream and VC-join in parallel,
    playing chunks as they arrive. Single process, no intermediate mp3 file."""
    async def say(client: discord.Client) -> dict:
        vc, err = _resolve_vc(client, cfg, text_channel_id)
        if err:
            return err
        if not allowlisted_present(_present_ids(vc), cfg.allow_user_ids):
            return {"ok": True, "played": False, "reason": "no allowlisted user in voice channel"}
        # Gate passed — kick off synthesis while the voice handshake runs
        read_fd, write_fd = os.pipe()
        reader = os.fdopen(read_fd, "rb")
        _start_tts_stream(text, voice_id, write_fd)
        voice = await vc.connect()
        try:
            voice.play(discord.FFmpegPCMAudio(reader, pipe=True))
            while voice.is_playing():
                await asyncio.sleep(0.3)
        finally:
            await voice.disconnect()
            reader.close()
        return {"ok": True, "played": True, "vc_id": str(vc.id), "vc_name": vc.name}
    return say


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice-mode routing for Discord TTS")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("channels", help="List guilds and their voice channels")
    p_check = sub.add_parser("check", help="Check whether voice mode is active for a text channel")
    p_check.add_argument("text_channel_id", type=int)
    p_play = sub.add_parser("play", help="Play an mp3 in the voice channel paired with a text channel")
    p_play.add_argument("text_channel_id", type=int)
    p_play.add_argument("mp3_path")
    p_say = sub.add_parser("say", help="Synthesize and play text in one shot (streaming TTS, no mp3 file)")
    p_say.add_argument("text_channel_id", type=int)
    p_say.add_argument("text")
    p_say.add_argument("--voice", default=os.getenv("TTS_VOICE_ID", ""),
                       help="ElevenLabs voice ID (default: TTS_VOICE_ID from .env)")
    args = parser.parse_args()

    cfg = None
    try:
        cfg = VoiceModeConfig.load()
    except FileNotFoundError:
        pass  # tolerated for `channels`, which is used to bootstrap the config
    except (ValueError, json.JSONDecodeError) as e:
        _emit({"ok": False, "error": f"config error: {e}"})
        return 1

    # Token can live in this repo's .env, or behind a token_file pointer in the
    # config (so a chat bot's existing token isn't duplicated across configs).
    global BOT_TOKEN
    if not BOT_TOKEN and cfg and cfg.token_file:
        load_dotenv(cfg.token_file)
        BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not BOT_TOKEN:
        _emit({"ok": False, "error": "DISCORD_BOT_TOKEN not set (.env or config token_file)"})
        return 1

    if args.cmd == "channels":
        action = cmd_channels
    else:
        if cfg is None:
            _emit({"ok": False, "error": f"config not found: {resolve_config_path()}"})
            return 1
        if not cfg.enabled:
            # Master switch off — answer without burning a gateway connect
            key = "active" if args.cmd == "check" else "played"
            _emit({"ok": True, key: False, "reason": "voice mode disabled"})
            return 0
        if args.cmd == "check":
            action = make_check(cfg, args.text_channel_id)
        elif args.cmd == "say":
            if not args.voice:
                _emit({"ok": False, "error": "no voice id — pass --voice or set TTS_VOICE_ID in .env"})
                return 1
            if not os.getenv("ELEVENLABS_API_KEY"):
                _emit({"ok": False, "error": "ELEVENLABS_API_KEY not set in .env"})
                return 1
            action = make_say(cfg, args.text_channel_id, args.text, args.voice)
        else:
            if not os.path.exists(args.mp3_path):
                _emit({"ok": False, "error": f"file not found: {args.mp3_path}"})
                return 1
            action = make_play(cfg, args.text_channel_id, args.mp3_path)

    result = asyncio.run(_with_client(action))
    _emit(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
