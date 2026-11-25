# -*- coding: utf-8 -*-
"""Правила игры и запись лога. Экраны живут в app.py."""

import json
import random
import shutil
import threading
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

DOORS = (1, 2, 3)
GROUPS = ("ПРИ", "ПИ")
ATTEMPTS = (1, 2, 3)

COLUMNS = [
    "id",
    "время",
    "фио",
    "знал_парадокс",
    "дверь_с_призом",
    "первый_выбор",
    "дверь_ведущего",
    "решение",
    "итоговая_дверь",
    "выиграл",
    "выиграл_бы_иначе",
    "что_выгоднее",
]
SUMMARY_COLUMNS = ["попытка", *COLUMNS]
OPINIONS = (
    "держаться первого выбора",
    "менять",
    "затрудняюсь сказать",
)

_lock = threading.Lock()


def choose_host_door(prize, first, rng=None):
    """Ведущий всегда открывает пустую дверь и никогда не трогает выбор игрока.

    Если игрок сразу попал в приз, обе остальные двери пустые, берём любую.
    Если игрок попал в пустую, открывается вторая пустая, без случайности.
    """
    if prize not in DOORS or first not in DOORS:
        raise ValueError("дверь вне 1..3")
    if rng is None:
        rng = random
    others = [door for door in DOORS if door != first]
    if first == prize:
        return rng.choice(others)
    for door in others:
        if door != prize:
            return door
    raise RuntimeError("ведущему нечего открыть")


def other_closed_door(first, host):
    """Вторая закрытая дверь: не выбор игрока и не та, что открыл ведущий."""
    left = [door for door in DOORS if door != first and door != host]
    if len(left) != 1:
        raise RuntimeError("после хода ведущего должна остаться одна чужая закрытая дверь")
    return left[0]


def judge(prize, final, first, host):
    """Фактический выигрыш и выигрыш, если бы на втором шаге взяли другую дверь.

    Считаем по дверям, а не как «просто наоборот»: если эти два флага совпали,
    в логе это видно и значит, что ведущий или итог посчитаны неверно.
    """
    if final == first:
        alternative = other_closed_door(first, host)
    else:
        alternative = first
    won = final == prize
    won_other = alternative == prize
    return won, won_other


def now_text():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def yes_no(flag):
    return "да" if flag else "нет"


def attempt_path(group, attempt):
    if group not in GROUPS:
        raise ValueError("неизвестная группа")
    if int(attempt) not in ATTEMPTS:
        raise ValueError("попытка должна быть 1, 2 или 3")
    return Path(__file__).resolve().parent / group / f"попытка_{int(attempt)}.xlsx"


def _queue_path(path):
    return path.with_name(path.stem + "_очередь.json")


def _read_queue(path):
    queue_path = _queue_path(path)
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    queue = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            queue.append({key: "" if item.get(key) is None else str(item.get(key)) for key in item})
    return queue


def _write_queue(path, queue):
    queue_path = _queue_path(path)
    temporary = queue_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    temporary.replace(queue_path)


def _clear_queue(path):
    queue_path = _queue_path(path)
    if queue_path.exists():
        queue_path.unlink()


def _upsert(rows, incoming):
    for row in rows:
        if row.get("id") == incoming["id"]:
            row.update(incoming)
            return
    fresh = {column: "" for column in COLUMNS}
    fresh.update(incoming)
    rows.append(fresh)


def _merge_partial(items, incoming):
    """В очереди храним только присланные поля, пустыми старые значения не затираем."""
    for item in items:
        if item.get("id") == incoming["id"]:
            item.update(incoming)
            return
    items.append(dict(incoming))


def _apply_queue(rows, queue):
    for item in queue:
        _upsert(rows, item)
    return rows


def _try_read_rows(path):
    """Читает xlsx. Если Excel держит файл, пробует снять копию: чтение обычно разрешено."""
    if not path.exists():
        return [], True
    try:
        return _read_rows(path), True
    except (PermissionError, OSError):
        pass
    temporary = path.with_name(path.stem + "_чтение.xlsx")
    try:
        shutil.copyfile(path, temporary)
        return _read_rows(temporary), True
    except (PermissionError, OSError):
        return [], False
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _flush(path, rows):
    """Пишет xlsx. Если он открыт в Excel, оставляет очередь и не мешает игре."""
    try:
        _write_rows(path, rows)
    except PermissionError:
        return False
    except OSError as exc:
        locked = getattr(exc, "winerror", None) in (32, 33) or exc.errno in (13,)
        if locked:
            return False
        raise
    _clear_queue(path)
    return True


_sheets_ready = False
_spreadsheet = None


def _use_sheets():
    """В облаке секреты есть, и результаты идут в Google Таблицу. На ноутбуке их нет, остаётся Excel."""
    try:
        import streamlit as st

        return "gcp_service_account" in st.secrets and bool(st.secrets.get("spreadsheet_id"))
    except Exception:
        return False


def _sheet_title(group, attempt):
    return f"{group} попытка {int(attempt)}"


def _summary_title(group):
    return f"{group} все результаты"


def _people_passed_phrase(count):
    number = abs(int(count))
    tail = number % 100
    last = tail % 10
    if last == 1 and not 11 <= tail <= 14:
        verb, noun = "прошёл", "человек"
    elif 2 <= last <= 4 and not 11 <= tail <= 14:
        verb, noun = "прошло", "человека"
    else:
        verb, noun = "прошло", "человек"
    return f"Всего {verb} {number} {noun}."


def _share_percents(counts):
    total = sum(counts)
    if total <= 0:
        return [0, 0, 0]
    raw = [count * 100 / total for count in counts]
    whole = [int(value) for value in raw]
    left = 100 - sum(whole)
    order = sorted(
        range(len(counts)),
        key=lambda index: (raw[index] - whole[index], counts[index]),
        reverse=True,
    )
    for index in order[:left]:
        whole[index] += 1
    return whole


def outcome_sentence(opinions):
    """Итог по ответам «что выгоднее»: сколько человек дошли до конца и как ответили."""
    counts = [sum(1 for item in opinions if item == choice) for choice in OPINIONS]
    total = sum(counts)
    if total == 0:
        return "Всего прошло 0 человек. Итогового ответа пока нет."
    stay, switch, unsure = _share_percents(counts)
    return (
        f"{_people_passed_phrase(total)} Из них "
        f"{stay}% выбирают «{OPINIONS[0]}», "
        f"{switch}% — «{OPINIONS[1]}», "
        f"{unsure}% — «{OPINIONS[2]}»."
    )


def _open_spreadsheet():
    global _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet
    import gspread
    import streamlit as st
    from google.oauth2.service_account import Credentials

    info = dict(st.secrets["gcp_service_account"])
    key = info.get("private_key")
    if isinstance(key, str):
        info["private_key"] = key.replace("\\n", "\n")
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    client = gspread.authorize(creds)
    _spreadsheet = client.open_by_key(str(st.secrets["spreadsheet_id"]))
    return _spreadsheet


def _sheet_by_title(title, columns):
    import gspread

    book = _open_spreadsheet()
    try:
        sheet = book.worksheet(title)
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title, rows=2000, cols=len(columns))
    header = sheet.row_values(1)
    if header != list(columns):
        sheet.update([list(columns)], "A1", value_input_option="RAW")
    return sheet


def _worksheet(group, attempt):
    return _sheet_by_title(_sheet_title(group, attempt), COLUMNS)


def _put_row(sheet, columns, key_name, record):
    values = sheet.get_all_values()
    if not values:
        values = [list(columns)]
    key_index = columns.index(key_name)
    row_number = None
    current = {column: "" for column in columns}
    for index, row in enumerate(values[1:], start=2):
        if len(row) > key_index and row[key_index] == record[key_name]:
            row_number = index
            for column, value in zip(columns, row):
                current[column] = "" if value is None else str(value)
            break
    current.update({key: value for key, value in record.items() if value is not None})
    payload = [current.get(column, "") for column in columns]
    if row_number is None:
        sheet.append_row(payload, value_input_option="USER_ENTERED")
    else:
        sheet.update([payload], f"A{row_number}", value_input_option="USER_ENTERED")
    return current


def _refresh_summary(group):
    summary = _sheet_by_title(_summary_title(group), SUMMARY_COLUMNS)
    existing = summary.get_all_values()
    id_index = SUMMARY_COLUMNS.index("id")
    known = set()
    for row in existing[1:]:
        if len(row) > id_index and row[id_index]:
            known.add(row[id_index])
    missing = []
    for attempt in ATTEMPTS:
        values = _worksheet(group, attempt).get_all_values()
        for row in values[1:]:
            if not row or not row[0] or row[0] in known:
                continue
            record = {"попытка": str(attempt)}
            for column, value in zip(COLUMNS, row):
                record[column] = "" if value is None else str(value)
            missing.append([record.get(column, "") for column in SUMMARY_COLUMNS])
            known.add(record["id"])
    if missing:
        summary.append_rows(missing, value_input_option="USER_ENTERED")
    _write_outcome_line(summary)


def _ensure_sheets():
    global _sheets_ready
    if _sheets_ready:
        return
    with _lock:
        if _sheets_ready:
            return
        try:
            for group in GROUPS:
                for attempt in ATTEMPTS:
                    _worksheet(group, attempt)
                _refresh_summary(group)
        except Exception as exc:
            raise OSError("Google Таблица недоступна. Проверьте, что к ней есть доступ у сервисного аккаунта.") from exc
        _sheets_ready = True


def _save_sheets(group, attempt, incoming):
    try:
        sheet = _worksheet(group, attempt)
        saved = _put_row(sheet, COLUMNS, "id", incoming)
        saved["попытка"] = str(int(attempt))
        summary = _sheet_by_title(_summary_title(group), SUMMARY_COLUMNS)
        _put_row(summary, SUMMARY_COLUMNS, "id", saved)
        _write_outcome_line(summary)
    except OSError:
        raise
    except Exception as exc:
        raise OSError("Строка в Google Таблицу не записалась. Нажмите кнопку ещё раз.") from exc


def _write_outcome_line(sheet):
    values = sheet.get_all_values()
    opinion_index = SUMMARY_COLUMNS.index("что_выгоднее")
    id_index = SUMMARY_COLUMNS.index("id")
    summary_rows = []
    opinions = []
    for index, row in enumerate(values[1:], start=2):
        first = row[0].strip() if row else ""
        if first.startswith("Всего прош"):
            summary_rows.append(index)
            continue
        if len(row) <= id_index or not row[id_index].strip():
            continue
        opinion = row[opinion_index].strip() if len(row) > opinion_index else ""
        if opinion in OPINIONS:
            opinions.append(opinion)
    for index in reversed(summary_rows):
        sheet.delete_rows(index)
    if opinions:
        sheet.append_row([outcome_sentence(opinions)], value_input_option="USER_ENTERED")


def ensure_workbooks():
    """Папка ПРИ и папка ПИ, в каждой три файла: попытка 1, 2 и 3.

    В облаке вместо файлов готовятся листы Google Таблицы:
    по попыткам и ещё один лист на группу со всеми результатами.
    Если Excel уже закрыт, сюда же дописываются ответы, которые копились, пока файл был открыт.
    """
    if _use_sheets():
        _ensure_sheets()
        return
    with _lock:
        for group in GROUPS:
            for attempt in ATTEMPTS:
                path = attempt_path(group, attempt)
                path.parent.mkdir(parents=True, exist_ok=True)
                queue = _read_queue(path)
                if queue:
                    rows, readable = _try_read_rows(path)
                    if readable:
                        _apply_queue(rows, queue)
                        _flush(path, rows)
                elif not path.exists():
                    try:
                        _write_rows(path, [])
                    except PermissionError:
                        pass


def save_progress(group, attempt, session_id, **fields):
    """Дописывает или обновляет одну строку. Открытый Excel игру не останавливает."""
    if not session_id:
        raise ValueError("нет id сессии")
    incoming = {"id": str(session_id)}
    for key, value in fields.items():
        if key not in COLUMNS:
            raise ValueError(f"неизвестное поле лога: {key}")
        if value is None:
            continue
        incoming[key] = str(value)

    if _use_sheets():
        with _lock:
            _save_sheets(group, attempt, incoming)
        return

    path = attempt_path(group, attempt)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        queue = _read_queue(path)
        rows, readable = _try_read_rows(path)
        if readable:
            _apply_queue(rows, queue)
            _upsert(rows, incoming)
            if _flush(path, rows):
                return
        _queue_update(path, incoming)


def _queue_update(path, incoming):
    queue = _read_queue(path)
    _merge_partial(queue, incoming)
    _write_queue(path, queue)


def _read_rows(path):
    book = load_workbook(path)
    sheet = book.active
    rows = []
    for cells in sheet.iter_rows(min_row=2, values_only=True):
        if not cells or cells[0] in (None, ""):
            continue
        row = {}
        for column, value in zip(COLUMNS, cells):
            row[column] = "" if value is None else str(value)
        rows.append(row)
    book.close()
    return rows


def _write_rows(path, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "результаты"
    sheet.append(COLUMNS)
    for row in rows:
        sheet.append([row.get(column, "") for column in COLUMNS])
    widths = {
        "фио": 34,
        "знал_парадокс": 34,
        "что_выгоднее": 28,
        "время": 20,
        "id": 16,
    }
    for index, column in enumerate(COLUMNS, start=1):
        letter = sheet.cell(1, index).column_letter
        sheet.column_dimensions[letter].width = widths.get(column, 18)
    book.save(path)
    book.close()


def self_check(games=4000, seed=7):
    """Жёсткие проверки из плана: ведущий не открывает приз, исходы противоположны."""
    rng = random.Random(seed)
    host_when_hit = {2: 0, 3: 0}
    switch_wins = 0
    stay_wins = 0

    for _ in range(games):
        prize = rng.choice(DOORS)
        first = rng.choice(DOORS)
        host = choose_host_door(prize, first, rng)

        if host == prize or host == first:
            raise AssertionError(f"ведущий открыл запрещённую дверь: приз={prize} выбор={first} ведущий={host}")
        if first != prize and host != other_closed_door(first, prize):
            raise AssertionError("при пустом первом выборе ведущий открыл не вторую пустую")
        if first == 1 and prize == 1:
            host_when_hit[host] = host_when_hit.get(host, 0) + 1

        other = other_closed_door(first, host)
        for final, name in ((first, "оставил"), (other, "сменил")):
            won, won_other = judge(prize, final, first, host)
            if won == won_other:
                raise AssertionError(f"исходы совпали ({name}), приз={prize} итог={final}")
            if name == "сменил":
                if won != (first != prize):
                    raise AssertionError("смена выигрывает не тогда, когда первая дверь пустая")
                switch_wins += int(won)
            else:
                if won != (first == prize):
                    raise AssertionError("сохранение выигрывает не тогда, когда первая дверь с призом")
                stay_wins += int(won)

    if host_when_hit[2] == 0 or host_when_hit[3] == 0:
        raise AssertionError(f"при точном первом выборе ведущий открывает не обе двери: {host_when_hit}")

    switch_rate = switch_wins / games
    stay_rate = stay_wins / games
    if not (0.62 <= switch_rate <= 0.72):
        raise AssertionError(f"доля побед при смене далека от 2/3: {switch_rate:.3f}")
    if not (0.28 <= stay_rate <= 0.38):
        raise AssertionError(f"доля побед при сохранении далека от 1/3: {stay_rate:.3f}")
    return {
        "games": games,
        "switch_rate": round(switch_rate, 4),
        "stay_rate": round(stay_rate, 4),
        "host_when_player_hit_door_1": host_when_hit,
    }
