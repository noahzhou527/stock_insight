from pathlib import Path

import pandas as pd
import streamlit as st


_ASSET_DIR = Path(__file__).resolve().parent / "assets"


def is_light_theme() -> bool:
    return st.context.theme.type == "light"


def load_styles(*names: str) -> None:
    if is_light_theme():
        names = (*names, "light.css")
    css = "\n".join((_ASSET_DIR / name).read_text(encoding="utf-8") for name in names)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


_BOOT_SKELETON = """
<div class="boot-skeleton" aria-hidden="true">
    <span class="sk-badge"></span>
    <span class="sk-title"></span>
    <span class="sk-sub"></span>
    <div class="boot-skeleton-grid">
        <span class="sk-card"></span>
        <span class="sk-card"></span>
        <span class="sk-card"></span>
        <span class="sk-card"></span>
    </div>
    <p class="boot-skeleton-note">正在载入工作台…</p>
</div>
"""

_BOOT_SKELETON_SIDEBAR = """
<div class="boot-skeleton boot-skeleton-side" aria-hidden="true">
    <span class="sk-card"></span>
    <span class="sk-card"></span>
    <span class="sk-card"></span>
    <span class="sk-card"></span>
</div>
"""
# 若运行中因旧模块缓存报 ImportError: render_boot_skeleton，需重启 Streamlit 进程。


def render_boot_skeleton() -> None:
    """浏览器记忆就绪前先铺一层骨架。

    sync_browser_state() 在拿到记忆之前会 st.stop() 空转一轮，那一轮如果什么都不画，
    页面就只剩右上角的 Streamlit 工具栏和一整屏空白底色，像加载失败。
    骨架跟随当前原生主题，浅色下就是浅色骨架。
    侧栏也占一下位，免得侧栏出现时整页横向跳一下。
    """
    st.markdown(_BOOT_SKELETON, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(_BOOT_SKELETON_SIDEBAR, unsafe_allow_html=True)


def themed_dataframe(frame):
    if not is_light_theme():
        return frame
    two_decimal_columns = {
        column: "{:.2f}%" if str(column).endswith("（%）") else "{:.2f}"
        for column in frame.columns
        if str(column) in {"开盘价", "最高价", "最低价", "收盘价", "RSI（相对强弱指标）"}
        or str(column).endswith(("（亿元）", "（%）"))
    }
    display = frame.copy()
    for column, number_format in two_decimal_columns.items():
        display[column] = display[column].map(
            lambda value, template=number_format: "—" if pd.isna(value) else template.format(value)
        )
    return display.style.set_properties(
        **{
            "background-color": "#ffffff",
            "color": "#172033",
            "border-color": "#dbe3ec",
        }
    ).set_table_styles(
        [
            {
                "selector": "th",
                "props": "background-color: #eef2f6; color: #172033; border-color: #dbe3ec;",
            },
            {
                "selector": "td",
                "props": "background-color: #ffffff; color: #172033; border-color: #dbe3ec;",
            },
        ]
    )


def render_dataframe(frame, **kwargs):
    if not is_light_theme():
        return st.dataframe(frame, **kwargs)
    table_kwargs = {
        "width": kwargs.get("width", "stretch"),
        "hide_index": kwargs.get("hide_index"),
    }
    if len(frame) > 12:
        table_kwargs["height"] = 680
    return st.table(themed_dataframe(frame), **table_kwargs)
