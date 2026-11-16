#!/usr/bin/env python3
"""Фоторадар: собирает из открытых источников объявления людей, которые ищут фотографа.

Источники (каждый включается сам, если для него есть ключи):
  - ВКонтакте: поиск по всем открытым постам + стены групп   (нужен VK_TOKEN)
  - Telegram-каналы: публичные каналы через t.me/s/           (ключи не нужны)
  - Telegram-чаты: через личный аккаунт                       (TG_API_ID, TG_API_HASH, TG_SESSION)
  - RSS бирж (FL.ru)                                          (ключи не нужны)

Результат: docs/data/leads.json и docs/data/status.json — их читает сайт.
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text("utf-8"))
DATA = ROOT / "docs" / "data"
LEADS_FILE = DATA / "leads.json"
STATUS_FILE = DATA / "status.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
NOW = time.time()
CUTOFF = NOW - CFG["max_age_hours"] * 3600


def log(*a):
    print(*a, flush=True)


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ───────────────────────── фильтр: «человек ищет фотографа» ─────────────────────────

NEED = (r"(?:ищу|ищем|ищет|ищется|нужен|нужна|нужно|нужны|требуется|требуются|необходим\w*|"
        r"разыскива\w+|в\s+поиск\w+|посоветуйте|подскажите|порекомендуйте|посоветует|"
        r"кто\s+(?:может|сможет|снимает|фотографирует|знает)|есть\s+(?:ли\s+)?(?:кто|тут|здесь)|"
        r"хочу|хотим|хочется|понадобится|нужд\w+)")
SUBJ = (r"(?:фотограф(?:а|у|ом|е|ы|ов|ам|ами|ах|иня|иню|иней)?\b|фотосесси\w+|фотосъ[её]мк\w+|съ[её]мк\w+|фотосет\w*|"
        r"пофотографир\w+|сфотографир\w+|отсня\w+)")
RE_DEMAND = re.compile(rf"\b{NEED}\b.{{0,70}}?\b{SUBJ}|\b{SUBJ}\b.{{0,40}}?\b{NEED}\b", re.I | re.S)
RE_STRONG = re.compile(r"\b(?:ищу|ищем|нужен|требуется|посоветуйте|подскажите|порекомендуйте)\s+"
                       r"(?:\w+\s+){0,3}фотограф(?:а|у|ом|е|ы|ов|ам|ами|ах)?\b", re.I)
# Объявления самих фотографов и поиск моделей — не то, что нужно
RE_OFFER = re.compile(
    r"я\s*[—–-]?\s*фотограф|фотограф\s+ищет|ищ(?:у|ем)\s+(?:\w+\s+){0,2}модел|нуж(?:на|ны)\s+модел|ищу\s+клиент|ищу\s+работу|"
    r"свободн\w+\s+(?:дат|окн|окош|мест)|запис\w+\s+на\s+(?:съ|фото)|открыт\w*\s+запись|"
    r"мо[её]\s+портфолио|провожу\s+(?:фото|съ)|предлагаю\s+(?:услуг|съ|фото)|"
    r"приглашаю\s+на\s+(?:съ|фото)|скидк\w+\s+на\s+(?:съ|фото)|фотограф\s+в\s+поиске\s+модел", re.I)

TAGS = [
    ("срочно", r"срочно|сегодня|завтра|на\s+выходны|в\s+эти\s+выходные|как\s+можно\s+скорее|asap"),
    ("новый год", r"нов\w+\s+год|новогод\w+|рождеств\w+|[её]лк\w+|зимн\w+\s+(?:фото|съ)"),
    ("свадьба", r"свадьб\w+|свадеб\w+|венчани\w+|роспис\w+|загс"),
    ("семья", r"семейн\w+|семь[яюией]\w*|с\s+ребенком|с\s+реб[её]нком|с\s+детьми"),
    ("дети", r"детск\w+|малыш\w+|новорожд\w+|ньюборн|крещени\w+|утренник\w*|выписк\w+"),
    ("беременность", r"беременн\w+|в\s+ожидании"),
    ("love story", r"love\s*story|лав\s*стори|парн\w+\s+(?:фото|съ)|для\s+пары"),
    ("мероприятие", r"мероприяти\w+|корпоратив\w*|день\s+рождени\w+|юбиле\w+|репортаж\w*|"
                    r"праздник\w*|концерт\w*|выпускн\w+|девичник\w*"),
    ("предметка", r"предметн\w+|каталог\w*|товар\w*|для\s+маркетплейс\w*|wildberries|ozon|вайлдбер\w+"),
    ("контент", r"контент\w*|для\s+соцсет\w+|для\s+блог\w+|рилс\w*|reels|личн\w+\s+бренд\w*"),
    ("портрет", r"портрет\w*|индивидуальн\w+\s+(?:фото|съ)|для\s+резюме|делов\w+\s+(?:фото|портрет)"),
    ("tfp", r"\btfp\b|\bтфп\b|бесплатн\w+|по\s+бартеру|бартер"),
    ("вакансия", r"ваканси\w+|в\s+штат|в\s+команду|зарплат\w+|оклад|график\s+работы"),
]
TAGS = [(name, re.compile(rx, re.I)) for name, rx in TAGS]
RE_PRICE = re.compile(r"\d[\d\s]{1,7}\s*(?:₽|руб|р\.|р\b|тыс|т\.р|к\b)|бюджет|оплат\w+|цена\s+договорн\w+|"
                      r"по\s+договор[её]нности|договоримся", re.I)
RE_CITY = re.compile(r"(?<![а-яёa-z])(?:" + "|".join(map(re.escape, CFG["city_words"])) + r")", re.I)


def classify(text, local, extra=""):
    """Возвращает список тегов, если текст похож на запрос «ищу фотографа», иначе None."""
    if re.match(r'^\s*(?:\d+[.)]\s*)?(?:[^\w\s]+\s*)*(?:стоп|stop|закрыто|неактуально|не\s+актуально|фотограф\s+найден)\b', text or '', re.I):
        return None
    if re.search(r'хочу\s+поснимать|может\s+кто[- ]то\s+ищет\s+фотографа', text or '', re.I):
        return None
    if not text or len(text) < 15:
        return None
    if not RE_DEMAND.search(text):
        return None
    if RE_OFFER.search(text) and not RE_STRONG.search(text):
        return None
    if not local and not RE_CITY.search(text + " " + extra):
        return None
    tags = [name for name, rx in TAGS if rx.search(text)]
    if RE_PRICE.search(text):
        tags.append("есть бюджет")
    return tags


def norm_hash(text):
    t = re.sub(r"[^a-zа-яё0-9]+", "", text.lower())[:220]
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]


def make_lead(src, uid, place, url, text, author, ts, tags):
    text = text.strip()
    return {
        "id": f"{src}:{uid}",
        "src": src,
        "place": place,
        "url": url,
        "text": text[:1500] + ("…" if len(text) > 1500 else ""),
        "author": author or "",
        "ts": int(ts),
        "found": int(NOW),
        "tags": tags,
        "h": norm_hash(text),
    }


# ───────────────────────────────── ВКонтакте ─────────────────────────────────

def vk_call(method, token, **params):
    params.update(access_token=token, v="5.199", lang="ru")
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.vk.com/method/{method}", data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        res = json.loads(r.read().decode("utf-8"))
    time.sleep(0.4)  # лимит VK: не больше 3 запросов в секунду
    if "error" in res:
        raise RuntimeError(f"VK {method}: {res['error'].get('error_msg')}")
    return res["response"]


def vk_names(resp):
    names = {}
    for p in resp.get("profiles", []):
        names[p["id"]] = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    for g in resp.get("groups", []):
        names[-g["id"]] = g.get("name", "")
    return names


def fetch_vk():
    token = os.environ.get("VK_TOKEN", "").strip()
    if not token:
        return None, "нет ключа VK_TOKEN"
    out, errors = [], []

    def handle(items, names, local, place_default=None):
        for it in items:
            ts = it.get("date", 0)
            text = it.get("text", "")
            if ts < CUTOFF or not text:
                continue
            owner, pid = it.get("owner_id"), it.get("id")
            from_id = it.get("from_id", owner)
            place = place_default or names.get(owner, "ВКонтакте")
            tags = classify(text, local, extra=place)
            if tags is None:
                continue
            out.append(make_lead("vk", f"{owner}_{pid}", place, f"https://vk.com/wall{owner}_{pid}",
                                 text, names.get(from_id, ""), ts, tags))

    for q in CFG["vk"]["queries"]:
        try:
            r = vk_call("newsfeed.search", token, q=q, count=100, extended=1, start_time=int(CUTOFF))
            handle(r.get("items", []), vk_names(r), local=False)
        except Exception as e:
            errors.append(str(e))
    for g in CFG["vk"]["groups"]:
        try:
            r = vk_call("wall.get", token, domain=g, count=40, extended=1)
            names = vk_names(r)
            gname = next((x.get("name") for x in r.get("groups", []) if x.get("screen_name") == g), g)
            handle(r.get("items", []), names, local=True, place_default=gname)
        except Exception as e:
            errors.append(f"{g}: {e}")
    note = "; ".join(sorted(set(errors)))[:300]
    if errors and not out and len(errors) >= len(CFG["vk"]["queries"]):
        return None, note
    return out, note


# ───────────────────────────── Telegram: публичные каналы ─────────────────────────────

RE_TG_POST = re.compile(r'data-post="([^"]+)"(.*?)(?=data-post="|\Z)', re.S)
RE_TG_TEXT = re.compile(r'<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>', re.S)
RE_TG_TIME = re.compile(r'<time datetime="([^"]+)"')
RE_TG_TITLE = re.compile(r'<meta property="og:title" content="(.*?)"')


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


SOURCE_REPORT = []

def record_source(key, title, url, kind, ok, scanned=0, matched=0, latest=0, note=''):
    SOURCE_REPORT.append(dict(id=key, title=title, url=url, kind=kind, ok=ok,
        checked=int(time.time()), scanned=scanned, matched=matched, latest=latest, note=note))


def relevant_text(text, local, extra=''):
    # National digests can mention multiple cities. Never take a photographer
    # request from Moscow just because the same digest contains Yekaterinburg.
    parts = re.split(r'(?m)(?=^\s*\d+[.)]\s*(?:\(|#))|(?=🎭)', text)
    if len(parts) > 1 and not local:
        selected = [p for p in parts if classify(p, False, extra=extra) is not None]
        return '\n'.join(selected) if selected else None
    return text if classify(text, local, extra=extra) is not None else None


def fetch_tg_web():
    out, errors, ok = [], [], 0
    chans = [(c, True) for c in CFG['telegram_channels']['local']] + \
            [(c, False) for c in CFG['telegram_channels']['other']]
    def one(target):
        name, local = target
        items, seen, scanned, latest, title = [], set(), 0, 0, name
        error = ''
        before = None
        try:
            for _ in range(min(3, int(CFG.get('telegram_web_pages', 1)))):
                url = f'https://t.me/s/{name}' + (f'?before={before}' if before else '')
                page = http_get(url, timeout=18)
                match = RE_TG_TITLE.search(page)
                if match:
                    title = html.unescape(match.group(1))
                posts = RE_TG_POST.findall(page)
                if not posts:
                    raise ValueError('Public post feed unavailable')
                ids, oldest = [], NOW
                for post_id, body in posts:
                    if post_id in seen:
                        continue
                    seen.add(post_id)
                    if '/' in post_id:
                        ids.append(int(post_id.rsplit('/',1)[1]))
                    tm, tt = RE_TG_TIME.findall(body), RE_TG_TEXT.search(body)
                    if not tm:
                        continue
                    ts = dt.datetime.fromisoformat(tm[-1]).timestamp()
                    latest, oldest = max(latest, ts), min(oldest, ts)
                    scanned += 1
                    if not tt or ts < CUTOFF:
                        continue
                    text = relevant_text(strip_html(tt.group(1)), local, extra=title)
                    if text is None:
                        continue
                    tags = classify(text, local, extra=title)
                    items.append(make_lead('tg', post_id, title, f'https://t.me/{post_id}', text, '', ts, tags))
                if not ids or oldest < CUTOFF or before == min(ids):
                    break
                before = min(ids)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'[:180]
        return name, title, items, scanned, latest, error
    # One bounded worker pool for all feeds, not one pool per feed.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, title, items, scanned, latest, error in pool.map(one, chans):
            available = scanned > 0
            if available:
                ok += 1
            if error:
                errors.append(f'{name}: {error}')
            out.extend(items)
            record_source('tg:'+name.lower(), title, 'https://t.me/'+name,
                'Telegram-канал', available, scanned, len(items), int(latest), error)
    note = f'Доступно {ok}/{len(chans)} каналов; проверено {sum(x["scanned"] for x in SOURCE_REPORT if x["kind"]=="Telegram-канал")} постов'
    if errors:
        note += '; ' + '; '.join(errors)
    return (out if ok or not chans else None), note[:600]


# ───────────────────────── Telegram: чаты (через личный аккаунт) ─────────────────────────


# Public groups can expose individual messages through Telegram's post widget.
# Only configured public usernames are fetched. No login or account data is used.
PENDING_TG_CURSORS = None

def parse_public_widget(page, username, message_id, place):
    expected = f'{username}/{message_id}'
    posts = RE_TG_POST.findall(page)
    for post_id, body in posts:
        if post_id.lower() != expected.lower():
            continue
        tm, tt = RE_TG_TIME.findall(body), RE_TG_TEXT.search(body)
        if not tm:
            raise ValueError('Widget has no publication date')
        ts = dt.datetime.fromisoformat(tm[-1]).timestamp()
        if not tt or ts < CUTOFF:
            return True, None
        text = strip_html(tt.group(1))
        tags = classify(text, True, extra=place)
        lead = None if tags is None else make_lead(
            'tg', expected, place, f'https://t.me/{expected}', text, '', ts, tags)
        return True, lead
    if 'tgme_widget_message_error' in page:
        return False, None
    raise ValueError('Unrecognized widget response; cursor preserved')


def fetch_tg_public():
    global PENDING_TG_CURSORS
    configs = CFG.get('telegram_public_chats', [])
    if not configs:
        return None, 'No public chats configured'
    state_path = DATA / 'tg-cursors.json'
    state = load_json(state_path, {})
    out, notes, successes = [], [], 0
    for cfg in configs:
        username = cfg['username'].lower()
        if not re.fullmatch(r'[a-z][a-z0-9_]{4,31}', username):
            notes.append('Invalid public username')
            continue
        initial = max(1, int(cfg['seed_message_id']) - 64)
        cursor = int(state.get(username, initial - 1))
        last_found = cursor
        scanned = 0
        failed = False
        def fetch_one(mid):
            page = http_get(f'https://t.me/{username}/{mid}?embed=1', timeout=15)
            return parse_public_widget(page, username, mid, cfg.get('title', username))
        # Bounded look-ahead tolerates deleted messages. Very large gaps need a new seed.
        with ThreadPoolExecutor(max_workers=4) as pool:
            while scanned < 128:
                ids = list(range(cursor + 1, cursor + 17))
                futures = [pool.submit(fetch_one, mid) for mid in ids]
                present = False
                for mid, future in zip(ids, futures):
                    try:
                        exists, lead = future.result()
                    except Exception as exc:
                        notes.append(f'{username}: {type(exc).__name__}; retry from {mid}')
                        failed = True
                        break
                    scanned += 1
                    if exists:
                        present = True
                        last_found = mid
                    if lead:
                        out.append(lead)
                if failed:
                    break
                if not present and (username in state or ids[-1] >= int(cfg['seed_message_id'])):
                    break
                cursor = ids[-1]
        record_source('tg:'+username, cfg.get('title',username), 'https://t.me/'+username,
            'Telegram-чат', not failed, scanned, len([x for x in out if x['id'].startswith('tg:'+username+'/')]),
            note=('Ошибка чтения; повторим позже' if failed else f'Последний доступный номер: {last_found}'))
        state[username] = last_found
        if not failed:
            successes += 1
        notes.append(f'{username}: checked {scanned}, last post {last_found}')
    # Main saves cursors only AFTER persisting leads, so interrupted writes don't lose posts.
    PENDING_TG_CURSORS = state
    return (out if successes or out else None), '; '.join(notes)[:500]


def fetch_tg_chats():
    api_id, api_hash = os.environ.get("TG_API_ID", "").strip(), os.environ.get("TG_API_HASH", "").strip()
    session = os.environ.get("TG_SESSION", "").strip()
    if not (api_id and api_hash and session):
        return None, "не подключён Telegram-аккаунт"
    from telethon.sessions import StringSession
    from telethon.sync import TelegramClient

    cfg = CFG["telegram_chats"]
    out, errors = [], []
    cutoff_dt = dt.datetime.fromtimestamp(CUTOFF, dt.timezone.utc)
    with TelegramClient(StringSession(session), int(api_id), api_hash) as client:
        targets = {}  # username -> (entity, local)
        if cfg.get("scan_joined"):
            # Все открытые группы, в которых состоит аккаунт. Закрытые (без @имени) не трогаем:
            # их сообщения не должны попадать на сайт.
            for d in client.iter_dialogs(limit=300):
                uname = getattr(d.entity, "username", None)
                if d.is_group and uname:
                    targets[uname.lower()] = (d.entity, True)
        for name, local in [(c, True) for c in cfg["local"]] + [(c, False) for c in cfg["other"]]:
            if name.lower() in targets:
                continue
            try:
                targets[name.lower()] = (client.get_entity(name), local)
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}")
        for uname, (ent, local) in targets.items():
            title = getattr(ent, "title", uname)
            try:
                for msg in client.iter_messages(ent, limit=150):
                    if msg.date < cutoff_dt:
                        break
                    text = msg.message or ""
                    tags = classify(text, local, extra=title)
                    if tags is None:
                        continue
                    s = msg.sender
                    author = " ".join(filter(None, [getattr(s, "first_name", None),
                                                    getattr(s, "last_name", None)])) if s else ""
                    out.append(make_lead("tg", f"{uname}/{msg.id}", title, f"https://t.me/{uname}/{msg.id}",
                                         text, author, msg.date.timestamp(), tags))
            except Exception as e:
                errors.append(f"{uname}: {type(e).__name__}")
    return out, (f"чатов: {len(targets)}" + ("; " + "; ".join(errors) if errors else ""))[:300]


# ───────────────────────────────── RSS бирж ─────────────────────────────────

def fetch_rss():
    out, errors, ok = [], [], 0
    for feed in CFG["rss"]:
        try:
            root = ET.fromstring(http_get(feed["url"]).encode("utf-8"))
        except Exception as e:
            errors.append(f"{feed['name']}: {e}")
            continue
        ok += 1
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = strip_html(item.findtext("description") or "")
            link = (item.findtext("link") or "").strip()
            try:
                ts = parsedate_to_datetime(item.findtext("pubDate")).timestamp()
            except Exception:
                ts = NOW
            if ts < CUTOFF or not link:
                continue
            text = f"{title}\n{desc}"
            tags = classify(text, feed.get("local", False))
            if tags is None:
                continue
            out.append(make_lead("rss", hashlib.sha1(link.encode()).hexdigest()[:14],
                                 feed["name"], link, text, "", ts, tags))
    if CFG["rss"] and not ok:
        return None, "; ".join(errors)[:300]
    return out, "; ".join(errors)[:300]


# ───────────────────────────── уведомления (Web Push) ─────────────────────────────


def fetch_trudvsem():
    cfg = CFG.get('trudvsem', {})
    if not cfg.get('enabled'):
        return None, 'Not configured'
    url = 'https://opendata.trudvsem.ru/api/v1/vacancies/region/' + cfg['region'] + '?' + urllib.parse.urlencode({'text':cfg['query'], 'limit':100})
    out, scanned, latest = [], 0, 0
    try:
        payload = json.loads(http_get(url, timeout=35))
        if str(payload.get('status')) != '200':
            raise ValueError('Unexpected open-data response')
        rows = payload.get('results',{}).get('vacancies',[])
        for row in rows:
            v = row.get('vacancy',{})
            scanned += 1
            title = v.get('job-name','')
            if not re.search(r'фотограф|фотосъ[её]м',title,re.I):
                continue
            addresses = v.get('addresses',{}).get('address',[])
            address = '; '.join(x.get('location','') for x in addresses)
            if cfg['city'].casefold() not in address.casefold():
                continue
            try:
                ts = dt.datetime.fromisoformat(v['creation-date']).replace(tzinfo=dt.timezone(dt.timedelta(hours=5))).timestamp()
            except (KeyError, ValueError):
                continue
            latest = max(latest,ts)
            if ts < CUTOFF or not v.get('vac_url','').startswith('https://trudvsem.ru/vacancy/card/'):
                continue
            salary = v.get('salary','')
            text = '\n'.join(filter(None,['Вакансия: '+title, v.get('company',{}).get('name'),
                strip_html(v.get('duty','')), 'Оплата: '+salary if salary else '', v.get('schedule'), address]))
            tags = ['вакансия'] + (['есть бюджет'] if salary else [])
            out.append(make_lead('jobs', 'trudvsem:'+v['id'], 'Работа России', v['vac_url'], text, '', ts, tags))
        record_source('trudvsem', 'Работа России — фотограф, Екатеринбург',
            'https://trudvsem.ru/vacancy/search', 'Вакансии', True, scanned, len(out), int(latest),
            'Только адреса в Екатеринбурге; по дате публикации')
        return out, f'Проверено {scanned} вакансий; подходят {len(out)}'
    except Exception as exc:
        record_source('trudvsem','Работа России', 'https://trudvsem.ru/vacancy/search','Вакансии',False, note=type(exc).__name__)
        return None, type(exc).__name__ + ': ' + str(exc)[:150]


def send_push(new_leads):
    subs_raw = os.environ.get("PUSH_SUBSCRIPTIONS", "").strip()
    key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not (subs_raw and key and new_leads):
        return
    from pywebpush import WebPushException, webpush
    subs = json.loads(subs_raw)
    if isinstance(subs, dict):
        subs = [subs]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    claims_sub = f"https://github.com/{repo}" if repo else "https://github.com"
    recent = [l for l in new_leads if l["ts"] > NOW - 6 * 3600] or new_leads[:1]
    if len(recent) > 4:
        payloads = [{"title": f"Фоторадар: {len(recent)} новых объявлений",
                     "body": recent[0]["text"][:140], "url": "./"}]
    else:
        payloads = [{"title": f"Ищут фотографа · {l['place']}"[:80],
                     "body": l["text"][:180], "url": l["url"]} for l in recent]
    for sub in subs:
        for p in payloads:
            try:
                webpush(sub, json.dumps(p, ensure_ascii=False), vapid_private_key=key,
                        vapid_claims={"sub": claims_sub}, ttl=6 * 3600)
            except WebPushException as e:
                log("push: ошибка", getattr(e.response, "status_code", ""), str(e)[:120])
    log(f"push: отправлено {len(payloads)} уведомл. на {len(subs)} устройств")


# ──────────────────────────────────── запуск ────────────────────────────────────

def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def main():
    SOURCE_REPORT.clear()
    DATA.mkdir(parents=True, exist_ok=True)
    old = load_json(LEADS_FILE, [])
    old_status = load_json(STATUS_FILE, {})
    known_ids = {l["id"] for l in old}
    known_h = {l["h"] for l in old}

    sources = [("vk", "ВКонтакте", fetch_vk), ("tg_web", "Telegram-каналы", fetch_tg_web),
               ("tg_public", "Telegram: открытые чаты", fetch_tg_public),
               ("tg_chats", "Telegram: дополнительные чаты (API)", fetch_tg_chats), ("rss", "Биржи", fetch_rss), ("jobs", "Работа России", fetch_trudvsem)]
    status_sources, new = {}, []
    for key, title, fn in sources:
        try:
            items, note = fn()
        except Exception as e:
            items, note = None, f"{type(e).__name__}: {e}"[:300]
        found = 0
        for l in items or []:
            if l["id"] in known_ids or l["h"] in known_h:
                continue
            known_ids.add(l["id"])
            known_h.add(l["h"])
            new.append(l)
            found += 1
        status_sources[key] = {"title": title, "ok": items is not None, "note": note or ""}
        log(f"{title}: {'ок' if items is not None else 'выкл'}, подошло {len(items or [])}, новых {found}"
            + (f" — {note}" if note else ""))

    keep_from = NOW - CFG["keep_days"] * 86400
    leads = sorted([l for l in new + old if l["ts"] >= keep_from], key=lambda l: -l["ts"])[:600]

    if new or len(leads) != len(old) or not LEADS_FILE.exists():
        LEADS_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=1), "utf-8")
    STATUS_FILE.write_text(json.dumps({'checked':int(NOW), 'sources':status_sources}, ensure_ascii=False, indent=1), 'utf-8')
    (DATA / 'sources.json').write_text(json.dumps({'checked':int(NOW), 'sources': SOURCE_REPORT}, ensure_ascii=False, indent=1), 'utf-8')
    if PENDING_TG_CURSORS is not None:
        (DATA / 'tg-cursors.json').write_text(json.dumps(PENDING_TG_CURSORS, indent=1), 'utf-8')
    log(f"Итого новых объявлений: {len(new)}, всего в ленте: {len(leads)}")
    try:
        send_push(new)
    except Exception as e:
        log("push: не удалось —", e)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = ROOT / ".env"  # локальный запуск: ключи можно положить в файл .env
    if env.exists():
        for line in env.read_text("utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    main()
