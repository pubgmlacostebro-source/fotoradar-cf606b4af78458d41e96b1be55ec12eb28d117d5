"""Подключение Telegram-аккаунта для чтения открытых чатов: python tools/tg_login.py

Запускаете сами, один раз. Понадобятся api_id и api_hash с https://my.telegram.org
(раздел «API development tools») и код, который Telegram пришлёт в приложение.
Скрипт сохранит строку сессии в .secrets/tg_session.txt — её нужно добавить в GitHub
как секрет TG_SESSION. Эта строка даёт доступ к аккаунту: никому её не показывайте.
Сборщик только читает сообщения в открытых группах и ничего не пишет.
"""
from pathlib import Path

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

ROOT = Path(__file__).resolve().parent.parent
api_id = int(input("api_id: ").strip())
api_hash = input("api_hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:  # спросит телефон и код
    out = ROOT / ".secrets" / "tg_session.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text(client.session.save(), "utf-8")
    me = client.get_me()
    print(f"\nГотово, вход выполнен: {me.first_name}.")
    print("Строка сессии сохранена в", out)
    print("Добавьте в GitHub три секрета: TG_API_ID, TG_API_HASH и TG_SESSION (содержимое этого файла).")
