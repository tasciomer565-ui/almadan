from __future__ import annotations

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def generate_values(subject: str) -> str:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_value = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_value = private_key.public_key().public_bytes(
        Encoding.X962,
        PublicFormat.UncompressedPoint,
    )
    return "\n".join(
        (
            f"VAPID_PUBLIC_KEY={urlsafe(public_value)}",
            f"VAPID_PRIVATE_KEY={urlsafe(private_value)}",
            f"VAPID_SUBJECT={subject}",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subject",
        default="mailto:support@almadan.app",
        help="VAPID contact URI, normally a mailto: address.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    values = generate_values(args.subject)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{values}\n", encoding="utf-8")
        print(f"VAPID values written to {args.output}")
        return

    print(values)


if __name__ == "__main__":
    main()
