"""Создаёт пару ключей для уведомлений (Web Push): python tools/make_push_keys.py

Открытый ключ кладётся в docs/push-key.txt (его видит сайт).
Закрытый — в .secrets/vapid_private.txt: его нужно добавить в GitHub как секрет
VAPID_PRIVATE_KEY и никому не показывать. Папка .secrets в репозиторий не попадает.
"""
import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parent.parent
pub_file = ROOT / "docs" / "push-key.txt"
priv_file = ROOT / ".secrets" / "vapid_private.txt"

if priv_file.exists() and "--force" not in sys.argv:
    sys.exit("Ключи уже созданы. Пересоздать: добавьте --force (старые подписки перестанут работать).")

b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
key = ec.generate_private_key(ec.SECP256R1())
priv = key.private_numbers().private_value.to_bytes(32, "big")
pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

priv_file.parent.mkdir(exist_ok=True)
priv_file.write_text(b64(priv), "utf-8")
pub_file.write_text(b64(pub), "utf-8")
print("Готово.\n  открытый ключ:", pub_file, "\n  закрытый ключ:", priv_file, "(→ секрет VAPID_PRIVATE_KEY)")
