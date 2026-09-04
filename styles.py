from pathlib import Path

import pandas as pd
import streamlit as st


_ASSET_DIR = Path(__file__).resolve().parent / "assets"


def is_light_theme() -> bool:
    return st.query_params.get("theme") == "light"


def load_styles(*names: str) -> None:
    if is_light_theme():
        names = (*names, "light.css")
    css = "\n".join((_ASSET_DIR / name).read_text(encoding="utf-8") for name in names)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_theme_toggle() -> None:
    light = is_light_theme()
    if st.button(
        "切换主题",
        key="theme_toggle",
        help=f"切换到{'暗色' if light else '亮色'}模式",
    ):
        st.query_params["theme"] = "dark" if light else "light"
        st.rerun()


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
