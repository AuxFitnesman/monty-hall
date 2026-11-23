# -*- coding: utf-8 -*-
"""Три двери: группы ПРИ и ПИ, до трёх попыток, Excel по попыткам."""

import random
import uuid
from pathlib import Path

import streamlit as st

import game

# ============================================================
# КАРТИНКА НА ПЕРВОЙ СТРАНИЦЕ
# Положите файл картинки в эту же папку, рядом с app.py,
# и впишите его имя в кавычки.
# Подойдут png, jpg, jpeg, webp.
# Например: PICTURE_FILE = "dveri.jpg"
# ============================================================
PICTURE_FILE = "jpeg/diting_result_aa246c29e51911f1a7ce7a044809a1f1_1.jpeg"

KNEW_OPTIONS = (
    "да, знаю, в чём там дело",
    "что-то слышал, правило не помню",
    "нет, первый раз",
)

OPINION_OPTIONS = (
    "держаться первого выбора",
    "менять",
    "затрудняюсь сказать",
)


def init_state():
    defaults = {
        "step": "home",
        "group": None,
        "knew": None,
        "attempt": 1,
        "sid": None,
        "prize": None,
        "first": None,
        "host": None,
        "decision": None,
        "final": None,
        "won": None,
        "won_other": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def remember(step_name, **fields):
    try:
        game.save_progress(
            st.session_state.group,
            st.session_state.attempt,
            st.session_state.sid,
            **fields,
        )
    except PermissionError:
        st.error(
            "Файл Excel открыт и не даёт записать строку. "
            "Закройте его и нажмите кнопку ещё раз."
        )
        return False
    except OSError as exc:
        st.error(f"Результат не записался: {exc}")
        return False
    st.session_state.step = step_name
    st.rerun()
    return True


def begin_attempt(attempt):
    sid = uuid.uuid4().hex[:12]
    prize = random.randint(1, 3)
    try:
        game.save_progress(
            st.session_state.group,
            attempt,
            sid,
            время=game.now_text(),
            знал_парадокс=st.session_state.knew,
            дверь_с_призом=prize,
        )
    except PermissionError:
        st.error(
            "Файл Excel открыт и не даёт записать строку. "
            "Закройте его и нажмите кнопку ещё раз."
        )
        return
    except OSError as exc:
        st.error(f"Результат не записался: {exc}")
        return
    st.session_state.attempt = attempt
    st.session_state.sid = sid
    st.session_state.prize = prize
    st.session_state.first = None
    st.session_state.host = None
    st.session_state.decision = None
    st.session_state.final = None
    st.session_state.won = None
    st.session_state.won_other = None
    st.session_state.step = "choose"
    st.rerun()


def pick_first(door):
    prize = st.session_state.prize
    host = game.choose_host_door(prize, door)
    if host == prize or host == door:
        st.error("Сбой: ведущий открыл не ту дверь. Обновите страницу и начните заново.")
        return
    st.session_state.first = door
    st.session_state.host = host
    remember("switch", первый_выбор=door, дверь_ведущего=host)


def pick_second(decision):
    first = st.session_state.first
    host = st.session_state.host
    prize = st.session_state.prize
    other = game.other_closed_door(first, host)
    final = first if decision == "оставил" else other
    won, won_other = game.judge(prize, final, first, host)
    if won == won_other:
        st.error("Сбой подсчёта. Обновите страницу и начните заново.")
        return
    st.session_state.decision = decision
    st.session_state.final = final
    st.session_state.won = won
    st.session_state.won_other = won_other
    if won or st.session_state.attempt >= 3:
        nxt = "result"
    else:
        nxt = "retry"
    remember(
        nxt,
        решение=decision,
        итоговая_дверь=final,
        выиграл=game.yes_no(won),
        выиграл_бы_иначе=game.yes_no(won_other),
    )


def door_card(number, kind, note):
    colors = {
        "closed": ("#f3f0e8", "#3f3c36", "закрыта"),
        "mine": ("#e4edf8", "#243e66", "ваш выбор"),
        "empty": ("#e5f0e6", "#245233", "пусто"),
        "goat": ("#e5f0e6", "#245233", "коза"),
        "prize": ("#f8efd2", "#6d5414", "приз"),
    }
    background, ink, title = colors[kind]
    note_html = f"<div style='margin-top:6px;font-size:14px;'>{note}</div>" if note else ""
    st.markdown(
        f"""
        <div style="border:1px solid #d9d3c7;border-radius:10px;padding:16px 8px 14px;
                    text-align:center;background:{background};color:{ink};min-height:118px;">
            <div style="font-size:13px;letter-spacing:.06em;">ДВЕРЬ {number}</div>
            <div style="font-size:22px;margin-top:8px;">{title}</div>
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_doors_second():
    first = st.session_state.first
    host = st.session_state.host
    columns = st.columns(3)
    for column, number in zip(columns, game.DOORS):
        with column:
            if number == host:
                door_card(number, "goat", "её открыл ведущий")
            elif number == first:
                door_card(number, "mine", "пока закрыта")
            else:
                door_card(number, "closed", "пока закрыта")


def show_doors_result():
    prize = st.session_state.prize
    final = st.session_state.final
    columns = st.columns(3)
    for column, number in zip(columns, game.DOORS):
        with column:
            kind = "prize" if number == prize else "empty"
            note = "вы остановились здесь" if number == final else ""
            door_card(number, kind, note)


def explanation():
    stayed = st.session_state.decision == "оставил"
    won = st.session_state.won
    if stayed and won:
        return (
            "Вы остались при своём выборе и выиграли. Так бывает примерно в одном случае из трёх: "
            "в этот раз приз с самого начала лежал за вашей дверью."
        )
    if stayed and not won:
        return (
            "Вы остались при своей двери, а приз был за другой. "
            "Один такой исход сам по себе ничего не доказывает."
        )
    if not stayed and won:
        return (
            "Вы сменили дверь и забрали приз. В этой задаче смена чаще выигрывает: "
            "ведущий, открыв пустую дверь, уже сообщил кое-что про две другие. "
            "Поэтому смена забирает приз примерно в двух случаях из трёх."
        )
    return (
        "Вы сменили дверь, а приз остался за первой. Так тоже случается. "
        "По одной партии этого не понять."
    )


def show_picture():
    path = Path(__file__).resolve().parent / PICTURE_FILE
    if PICTURE_FILE and path.is_file():
        st.image(str(path), width="stretch")
        return
    st.markdown(
        """
        <div style="border:2px dashed #c8bfb2;border-radius:16px;min-height:280px;
                    display:flex;align-items:center;justify-content:center;
                    color:#8a8175;text-align:center;padding:24px;margin:8px 0 28px;">
            Здесь будет картинка
        </div>
        """,
        unsafe_allow_html=True,
    )


def screen_home():
    st.title("Три двери")
    show_picture()
    st.write("")
    if st.button("Далее", type="primary"):
        st.session_state.step = "faculty"
        st.rerun()


def screen_faculty():
    st.markdown(
        """
        <h1 style="text-align:center;font-size:2.1rem;line-height:1.25;
                   margin:0.2rem 0 0.8rem;font-weight:700;">Факультет — КТиИБ</h1>
        <p style="text-align:center;font-size:1.35rem;line-height:1.45;margin:0.4rem 0 0.2rem;">
            Привет! Пожалуйста, укажи, какое направление ты представляешь :)
        </p>
        <p style="text-align:center;font-size:1.05rem;line-height:1.45;color:#5c5348;margin:0 0 0.6rem;">
            (ПРИ — прикладная информатика; ПИ — программная инженерия)
        </p>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns(2, gap="large")
    with left:
        if st.button("ПРИ", key="pick_pri", width="stretch"):
            st.session_state.group = "ПРИ"
            st.session_state.step = "name"
            st.rerun()
    with right:
        if st.button("ПИ", key="pick_pi", width="stretch"):
            st.session_state.group = "ПИ"
            st.session_state.step = "name"
            st.rerun()


def screen_name():
    st.markdown(
        """
        <p style="font-size:1.35rem;line-height:1.55;margin:1.2rem 0 2rem;">
            Привет! Мы начинаем игру, чтобы дальше всё прошло успешно
            и стало понятно, какое направление справилось лучше.
            Это соревнование между группами, и оно ни на что не влияет.
        </p>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns(2)
    with left:
        if st.button("Назад"):
            st.session_state.step = "faculty"
            st.rerun()
    with right:
        if st.button("Далее", type="primary"):
            st.session_state.step = "know"
            st.rerun()


def screen_know():
    st.caption(st.session_state.group)
    knew = st.radio(
        "Слышал ли ты когда-то о таком парадоксе?",
        KNEW_OPTIONS,
        index=None,
        key="knew_radio",
    )
    if st.button("К дверям", type="primary"):
        if knew is None:
            st.warning("Сначала ответьте на вопрос выше.")
        else:
            st.session_state.knew = knew
            begin_attempt(1)


def screen_choose():
    st.caption(f"{st.session_state.group} · попытка {st.session_state.attempt}")
    st.write(
        "За одной из трёх дверей — приз, за двумя другими — козы. "
        "Какую дверь ты выберешь?"
    )
    columns = st.columns(3)
    attempt = st.session_state.attempt
    for column, number in zip(columns, game.DOORS):
        with column:
            if st.button(f"Дверь {number}", key=f"pick_{attempt}_{number}"):
                pick_first(number)


def screen_switch():
    host = st.session_state.host
    other = game.other_closed_door(st.session_state.first, host)
    attempt = st.session_state.attempt
    st.subheader("Ведущий открыл дверь")
    st.write(
        f"Ведущий открыл дверь {host}. Там оказалась коза. "
        "Остались две закрытые двери."
    )
    show_doors_second()
    st.write("")
    left, right = st.columns(2)
    with left:
        if st.button(f"Оставить дверь {st.session_state.first}", key=f"stay_{attempt}"):
            pick_second("оставил")
    with right:
        if st.button(f"Поменять на дверь {other}", key=f"switch_{attempt}"):
            pick_second("сменил")


def screen_retry():
    if st.session_state.attempt == 1:
        st.subheader("Коза-дереза!")
        st.write(
            "За твоей дверью коза: приз оказался в другом месте. "
            "Двери можно разложить заново и испытать удачу ещё раз."
        )
        yes_label = "Да, ещё раз"
    else:
        st.subheader("Снова мимо")
        st.write(
            "Второй раз дверь оказалась пустой. Остался последний шанс "
            "проверить, за какой дверью прячется приз."
        )
        yes_label = "Да, последний раз"
    left, right = st.columns(2)
    with left:
        if st.button(yes_label):
            begin_attempt(st.session_state.attempt + 1)
    with right:
        if st.button("Нет, хватит"):
            st.session_state.step = "result"
            st.rerun()


def screen_result():
    won = st.session_state.won
    prize = st.session_state.prize
    st.subheader("Вы выиграли" if won else "В этот раз приз не ваш")
    st.write(f"Приз лежал за дверью {prize}.")
    show_doors_result()
    st.write("")
    st.write(explanation())
    st.divider()
    opinion = st.radio(
        "Как вам кажется, что выгоднее?",
        OPINION_OPTIONS,
        index=None,
        key="opinion",
    )
    if st.button("Ответить", type="primary"):
        if opinion is None:
            st.warning("Выберите один вариант. Если не решили, отметьте «затрудняюсь сказать».")
        else:
            remember("thanks", что_выгоднее=opinion)


def screen_thanks():
    outcome = "выиграли" if st.session_state.won else "не выиграли"
    st.subheader("Спасибо")
    st.write(f"Ваш результат: вы {outcome}. На этом всё.")
    st.write(
        "Пока остальные не прошли, не рассказывайте, чем у вас кончилось "
        "и что, по-вашему, было выгоднее."
    )


def page_style(step):
    base = ".block-container {padding-top: 1.4rem; max-width: 760px;}"
    buttons = "div[data-testid='stButton'] > button {width: 100%;}"
    if step == "home":
        buttons = """
        div[data-testid='stVerticalBlock'] > div[data-testid='stElementContainer']:has(button) {
            align-self: flex-end;
        }
        div[data-testid='stButton'] > button {width: auto; min-width: 7.5rem;}
        """
    elif step == "faculty":
        base = ".block-container {padding-top: 1rem; max-width: 1040px;}"
        buttons = """
        div[data-testid='stColumn'] [data-testid='stElementContainer'],
        div[data-testid='stColumn'] [data-testid='stButton'] {width: 100%;}
        div[data-testid='stButton'] > button {
            width: 100%;
            height: 48vh;
            min-height: 240px;
            font-size: 4rem;
            font-weight: 700;
            letter-spacing: .08em;
            border: none;
            border-radius: 28px;
            background: #f3e6d2;
            color: #3c3228;
            box-shadow: 0 10px 28px rgba(90, 64, 32, 0.10);
        }
        div[data-testid='stButton'] > button:hover {
            background: #e8d3b6;
            color: #3c3228;
            border: none;
        }
        """
    hide_anchor = "[data-testid='stHeaderActionElements']{display:none !important;}"
    st.markdown(f"<style>{base}{buttons}{hide_anchor}</style>", unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="Три двери", page_icon="🚪", layout="centered")
    game.ensure_workbooks()
    init_state()
    step = st.session_state.step
    page_style(step)
    screens = {
        "home": screen_home,
        "faculty": screen_faculty,
        "name": screen_name,
        "know": screen_know,
        "choose": screen_choose,
        "switch": screen_switch,
        "retry": screen_retry,
        "result": screen_result,
        "thanks": screen_thanks,
    }
    screens.get(step, screen_home)()


if __name__ == "__main__":
    main()
