from pathlib import Path

import streamlit as st


_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"


def load_styles(*names: str) -> None:
    css = "\n".join((_ASSET_DIR / name).read_text(encoding="utf-8") for name in names)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
