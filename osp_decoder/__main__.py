"""Command line entry point; every option can also be set by an environment variable."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from collections.abc import Sequence
from pathlib import Path

from .service import AudioConfig, Config, DecoderConfig, DecoderService, ServerConfig


def _env(name: str, default: str) -> str:
    return os.environ.get(f"OSP_{name}", default)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line options with defaults taken from OSP_* variables."""
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="osp-decoder",
        description="Decode selective calls from audio and publish them over WebSocket.",
    )
    parser.add_argument(
        "--source-name",
        default=_env("SOURCE_NAME", defaults.source_name),
        help="value of the 'source' field of events (OSP_SOURCE_NAME)",
    )
    parser.add_argument(
        "--input-file",
        default=_env("INPUT_FILE", ""),
        help="decode an audio file instead of the sound card; '-' reads raw "
        "mono S16_LE 22050 Hz audio from stdin (OSP_INPUT_FILE)",
    )
    parser.add_argument(
        "--usb-id",
        default=_env("USB_ID", defaults.audio.usb_id),
        help="USB VID:PID of the sound card (OSP_USB_ID)",
    )
    parser.add_argument(
        "--alsa-device",
        default=_env("ALSA_DEVICE", ""),
        help="explicit ALSA capture device, overrides --usb-id (OSP_ALSA_DEVICE)",
    )
    parser.add_argument(
        "--protocols",
        default=_env("PROTOCOLS", ",".join(defaults.decoder.protocols)),
        help="comma-separated multimon-ng demodulators (OSP_PROTOCOLS)",
    )
    parser.add_argument(
        "--host",
        default=_env("HOST", defaults.server.host),
        help="WebSocket listen address (OSP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(_env("PORT", str(defaults.server.port))),
        help="WebSocket listen port (OSP_PORT)",
    )
    parser.add_argument(
        "--call-window",
        type=float,
        default=float(_env("CALL_WINDOW", str(defaults.decoder.call_window))),
        help="seconds within which an STQC command must follow its address "
        "to form a call (OSP_CALL_WINDOW)",
    )
    parser.add_argument(
        "--names-file",
        default=_env("NAMES_FILE", ""),
        help="JSON file with names of STQC areas, units and commands "
        "(OSP_NAMES_FILE)",
    )
    parser.add_argument(
        "--wait-for-receiver",
        action="store_true",
        default=_env("WAIT_FOR_RECEIVER", "") == "1",
        help="decode an input file only after a receiver connects (OSP_WAIT_FOR_RECEIVER=1)",
    )
    parser.add_argument(
        "--log-level",
        default=_env("LOG_LEVEL", "INFO"),
        help="logging level (OSP_LOG_LEVEL)",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    """Convert parsed options into the service configuration."""
    protocols = tuple(p.strip().upper() for p in args.protocols.split(",") if p.strip())
    return Config(
        source_name=args.source_name,
        audio=AudioConfig(
            input_file=Path(args.input_file) if args.input_file else None,
            usb_id=args.usb_id,
            alsa_device=args.alsa_device or None,
        ),
        decoder=DecoderConfig(
            protocols=protocols,
            call_window=args.call_window,
            names_file=Path(args.names_file) if args.names_file else None,
        ),
        server=ServerConfig(host=args.host, port=args.port),
        wait_for_receiver=args.wait_for_receiver,
    )


async def _serve(config: Config) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    await DecoderService(config).run(stop)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the decoder service."""
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Status requests are logged by websockets as rejected handshakes.
    logging.getLogger("websockets.server").setLevel(logging.WARNING)
    asyncio.run(_serve(build_config(args)))


if __name__ == "__main__":
    main()
