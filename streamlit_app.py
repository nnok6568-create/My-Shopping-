"""쇼핑리스트 — Streamlit 버전.

PRD.md의 기능(추가, 수정, 삭제, 체크, 저장)을 HTML 버전(index.html, app.js)과 같은 데이터 모델로 구현한다.
브라우저 localStorage 대신 이 파일 옆의 shopping_list.json에 저장한다.

실행: python -m streamlit run streamlit_app.py
"""

import json
import os
import time
import uuid
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).with_name("shopping_list.json")
MAX_NAME_LENGTH = 100

# 마크다운/HTML로 해석될 수 있는 문자. 화면에 출력할 때 모두 HTML 엔티티로 바꿔서 글자 그대로 보이게 한다 (XSS 방지)
SPECIAL_CHARS = set("&<>\"'\\`*_{}[]()#+-.!|~$:=")
# 위젯 라벨에서 서식(굵게, 수식, 링크, 이모지 코드 등)으로 해석되는 문자
LABEL_FORMAT_CHARS = set("\\`*_~$[]<>#:")


# ---------- 데이터 ----------

def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return str(uuid.uuid4())


def escape_text(text: str) -> str:
    """st.markdown(unsafe_allow_html=True)로 출력할 텍스트용."""
    return "".join(f"&#{ord(c)};" if c in SPECIAL_CHARS else c for c in text)


def plain_label(text: str) -> str:
    """숨겨진 위젯 라벨용. 라벨도 마크다운으로 해석되고 원문이 그대로 aria-label이 되므로,
    백슬래시로 이스케이프하는 대신 서식 문자를 빼서 화면 낭독기가 읽기 좋은 이름을 만든다."""
    cleaned = "".join(" " if c in LABEL_FORMAT_CHARS else c for c in text)
    return " ".join(cleaned.split())


def load_items() -> list[dict]:
    """저장 파일에서 아이템 목록을 읽는다. 파일이 없거나 깨졌으면 빈 목록으로 시작한다."""
    if "memory_items" in st.session_state:  # 저장 실패 후에는 이 세션의 메모리에만 유지
        return st.session_state.memory_items
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    items, seen_ids = [], set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("name"), str):
            continue
        # id가 중복되면 체크/삭제가 엉뚱한 아이템에 적용되므로, 두 번째부터는 새 id를 발급한다
        item_id = new_id() if item["id"] in seen_ids else item["id"]
        seen_ids.add(item_id)
        created_at = item.get("createdAt")
        items.append({
            "id": item_id,
            "name": item["name"],
            "checked": bool(item.get("checked")),
            "createdAt": created_at if isinstance(created_at, (int, float)) and not isinstance(created_at, bool) else now_ms(),
        })
    return items


def save_items(items: list[dict]) -> None:
    """임시 파일에 쓴 뒤 교체해서, 쓰는 도중 실패해도 기존 파일이 깨지지 않게 한다."""
    if "memory_items" in st.session_state:
        st.session_state.memory_items = items
        return
    try:
        tmp = DATA_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, DATA_FILE)
    except OSError:
        st.session_state.memory_items = items


def mutate(change) -> None:
    """상태 변경의 공통 흐름: 최신 파일 읽기 → 변경 → 저장. 다른 탭에서 바꾼 내용도 덮어쓰지 않는다."""
    items = load_items()
    change(items)
    save_items(items)


# ---------- 콜백 (버튼/체크박스를 누르면 화면을 다시 그리기 전에 실행) ----------

def add_item() -> None:
    name = st.session_state.new_item.strip()
    if not name:
        return
    mutate(lambda items: items.append({"id": new_id(), "name": name, "checked": False, "createdAt": now_ms()}))


def set_checked(item_id: str) -> None:
    checked = st.session_state[f"chk_{item_id}"]

    def change(items):
        for item in items:
            if item["id"] == item_id:
                item["checked"] = checked

    mutate(change)


def start_edit(item_id: str, name: str) -> None:
    st.session_state[f"edit_{item_id}"] = name
    st.session_state.editing_id = item_id


def save_edit(item_id: str) -> None:
    name = st.session_state[f"edit_{item_id}"].strip()
    st.session_state.editing_id = None
    if not name:  # 빈 값이면 원래 값 유지
        return

    def change(items):
        for item in items:
            if item["id"] == item_id:
                item["name"] = name

    mutate(change)


def cancel_edit() -> None:
    st.session_state.editing_id = None


def delete_item(item_id: str) -> None:
    if st.session_state.get("editing_id") == item_id:
        st.session_state.editing_id = None
    mutate(lambda items: items.__setitem__(slice(None), [i for i in items if i["id"] != item_id]))


def clear_checked() -> None:
    mutate(lambda items: items.__setitem__(slice(None), [i for i in items if not i["checked"]]))


@st.dialog("체크된 항목 삭제")
def confirm_clear(count: int) -> None:
    st.write(f"체크된 항목 {count}개를 삭제할까요?")
    delete_col, cancel_col = st.columns(2)
    if delete_col.button("삭제", type="primary", width="stretch"):
        clear_checked()
        st.rerun()
    if cancel_col.button("취소", width="stretch"):
        st.rerun()


# ---------- 화면 ----------

st.set_page_config(page_title="쇼핑리스트", page_icon="🛒", layout="centered")
st.session_state.setdefault("editing_id", None)

st.markdown(
    """
    <style>
      .block-container { max-width: 560px; padding-top: 2.5rem; }
      .item-name { display: block; padding: 0.25rem 0; word-break: keep-all; overflow-wrap: anywhere; }
      .item-name.checked { color: #6b6158; text-decoration: line-through; text-decoration-thickness: 1.5px; }
      .empty-message { padding: 2rem 0; text-align: center; color: #6b6158; }
      .progress-text { font-weight: 600; color: #6b6158; font-variant-numeric: tabular-nums; }
      /* 아이템 한 줄: 좁은 화면에서도 열이 세로로 쌓이지 않게 한 줄로 유지 */
      [class*="st-key-row-"] { border-bottom: 1px solid #ece3d8; padding: 0.25rem 0; }
      [class*="st-key-row-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: 0.25rem; align-items: center; }
      [class*="st-key-row-"] [data-testid="stColumn"] { min-width: 0 !important; }
      [class*="st-key-row-"] [data-testid="stColumn"]:has(> div > [data-testid="stElementContainer"] button),
      [class*="st-key-row-"] [data-testid="stColumn"]:has([data-testid="stCheckbox"]) { flex: 0 0 auto !important; width: auto !important; }
      [class*="st-key-row-"] button { min-height: 44px; min-width: 44px; }
      [class*="st-key-del_"] button p { color: #b91c1c; }
      .st-key-add-row [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: 0.5rem; }
      .st-key-add-row [data-testid="stColumn"] { min-width: 0 !important; }
      .st-key-add-row [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; width: auto !important; }
      .st-key-add-row input { min-height: 44px; }
      .st-key-add-row button { min-height: 44px; padding: 0 1.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🛒 쇼핑리스트")

# 추가: 폼으로 감싸서 Enter와 추가 버튼 모두 같은 동작 (st.form에는 키 클래스가 붙지 않아 컨테이너로 감싼다)
with st.container(key="add-row"), st.form("add-form", clear_on_submit=True, border=False):
    input_col, button_col = st.columns([0.78, 0.22], vertical_alignment="center")
    input_col.text_input(
        "추가할 아이템", key="new_item", placeholder="아이템 입력...",
        max_chars=MAX_NAME_LENGTH, label_visibility="collapsed",
    )
    button_col.form_submit_button("추가", type="primary", on_click=add_item, width="stretch")

if "memory_items" in st.session_state:
    st.warning("저장 파일에 쓸 수 없어서, 이 브라우저 세션에만 임시로 저장하고 있어요.")

items = load_items()

for item in items:
    item_id, name = item["id"], item["name"]
    with st.container(key=f"row-{item_id}"):
        check_col, body_col = st.columns([0.1, 0.9], vertical_alignment="center")

        # 체크박스 상태는 매번 저장 파일 값으로 맞춘다 (다른 탭에서 바뀐 값 반영)
        st.session_state[f"chk_{item_id}"] = item["checked"]
        check_col.checkbox(
            f"{plain_label(name)} 구매 완료", key=f"chk_{item_id}", on_change=set_checked, args=(item_id,),
            label_visibility="collapsed",
        )

        with body_col:
            if st.session_state.editing_id == item_id:
                # 폼 안에서 Enter를 누르면 첫 번째 버튼(저장)을 누른 것과 같다
                with st.form(f"edit-form-{item_id}", border=False):
                    edit_col, save_col, cancel_col = st.columns([0.6, 0.2, 0.2], vertical_alignment="center")
                    edit_col.text_input(
                        "아이템 이름 수정", key=f"edit_{item_id}", max_chars=MAX_NAME_LENGTH,
                        label_visibility="collapsed",
                    )
                    save_col.form_submit_button("저장", on_click=save_edit, args=(item_id,), type="tertiary")
                    cancel_col.form_submit_button("취소", on_click=cancel_edit, type="tertiary")
            else:
                name_col, edit_col, delete_col = st.columns([0.7, 0.15, 0.15], vertical_alignment="center")
                checked_class = " checked" if item["checked"] else ""
                name_col.markdown(f'<span class="item-name{checked_class}">{escape_text(name)}</span>', unsafe_allow_html=True)
                edit_col.button("수정", key=f"edit_btn_{item_id}", on_click=start_edit, args=(item_id, name), type="tertiary")
                delete_col.button("삭제", key=f"del_{item_id}", on_click=delete_item, args=(item_id,), type="tertiary")

if not items:
    st.markdown('<p class="empty-message">쇼핑리스트가 비어 있어요</p>', unsafe_allow_html=True)

checked_count = sum(item["checked"] for item in items)
progress_col, clear_col = st.columns([0.5, 0.5], vertical_alignment="center")
progress_col.markdown(f'<span class="progress-text">{checked_count} / {len(items)} 완료</span>', unsafe_allow_html=True)
if clear_col.button("체크된 항목 삭제", disabled=checked_count == 0, width="stretch"):
    confirm_clear(checked_count)
