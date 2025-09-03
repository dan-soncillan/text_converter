import streamlit as st
import re
import json
from typing import Dict, List, Tuple

st.set_page_config(page_title="Indent Format Transformer", layout="wide")

# ----------------------------
# Utilities
# ----------------------------
ZERO_WIDTH = "\u200B\u200C\u200D\uFEFF"
BULLET_CHARS = "\-\*\u2022\u2023\u2043\u2219\u25E6\u30FB\u00B7\u204C\u204D\u2212\u2013\u2014\u2015\u2043\u204C\u204D"
NUM_MARKER_RE = re.compile(r"^(\d+|[a-zA-Z]|[ivxIVX]+)[\)\.]\s+")
BULLET_RE = re.compile(rf"^[{BULLET_CHARS}]\s+")
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
LEADING_WS_RE = re.compile(r"^([ \t]*)(.*)$")
ZERO_WIDTH_RE = re.compile(f"[{ZERO_WIDTH}]")
SMART_QUOTES = {
    "“": '"', "”": '"', "„": '"', "′": "'", "’": "'", "‘": "'",
    "‛": "'", "‹": "<", "›": ">",
}

def normalize_text(text: str, convert_smart_quotes: bool = True) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ")  # NBSP -> space
    text = text.replace("\u3000", "  ")  # full-width space -> two spaces
    text = ZERO_WIDTH_RE.sub("", text)  # strip zero-width
    if convert_smart_quotes:
        for k, v in SMART_QUOTES.items():
            text = text.replace(k, v)
    return text


def extract_code_fences(text: str) -> Tuple[str, Dict[str, str]]:
    blocks: Dict[str, str] = {}

    def _repl(m: re.Match) -> str:
        key = f"__CODEBLOCK_{len(blocks)}__"
        blocks[key] = m.group(0)
        return key

    return CODE_FENCE_RE.sub(_repl, text), blocks


def restore_code_fences(text: str, blocks: Dict[str, str]) -> str:
    for k, v in blocks.items():
        text = text.replace(k, v)
    return text


def unify_markers(line: str) -> str:
    # bullets -> "- "; numbered markers "1)" -> "1. "
    if BULLET_RE.match(line):
        line = BULLET_RE.sub("- ", line)
    if NUM_MARKER_RE.match(line):
        line = NUM_MARKER_RE.sub(lambda m: f"{m.group(1)}. ", line)
    return line


def lines_to_markdown(lines: List[str], indent_size: int = 2, trim_trailing_ws: bool = True) -> List[str]:
    out: List[str] = []
    for raw in lines:
        if not raw.strip():
            out.append("")
            continue
        expanded = raw.expandtabs(indent_size)
        m = LEADING_WS_RE.match(expanded)
        leading, rest = (m.group(1), m.group(2)) if m else ("", expanded)
        level = len(leading) // indent_size
        rest = unify_markers(rest)
        line = f"{' ' * (indent_size * level)}{rest}"
        if trim_trailing_ws:
            line = line.rstrip()
        out.append(line)
    return out


def lines_to_gdocs(lines: List[str], indent_size: int = 2, bullet_symbol: str = "•", trim_trailing_ws: bool = True) -> List[str]:
    out: List[str] = []
    for raw in lines:
        if not raw.strip():
            out.append("")
            continue
        expanded = raw.expandtabs(indent_size)
        m = LEADING_WS_RE.match(expanded)
        leading, rest = (m.group(1), m.group(2)) if m else ("", expanded)
        level = len(leading) // indent_size
        rest = unify_markers(rest)
        # Convert normalized "- " to preferred symbol
        rest = re.sub(r"^\-\s+", f"{bullet_symbol} ", rest)
        line = f"{'\t' * level}{rest}"
        if trim_trailing_ws:
            line = line.rstrip()
        out.append(line)
    return out


def lines_to_plain(lines: List[str], indent_size: int = 2, trim_trailing_ws: bool = True) -> List[str]:
    out: List[str] = []
    for raw in lines:
        expanded = raw.expandtabs(indent_size)
        if trim_trailing_ws:
            expanded = expanded.rstrip()
        out.append(expanded)
    return out


def to_json_outline(lines: List[str], indent_size: int = 2) -> str:
    items: List[Dict] = []
    for raw in lines:
        if not raw.strip():
            continue
        expanded = raw.expandtabs(indent_size)
        m = LEADING_WS_RE.match(expanded)
        leading, rest = (m.group(1), m.group(2)) if m else ("", expanded)
        level = len(leading) // indent_size
        txt = unify_markers(rest)
        items.append({"level": level, "text": txt})
    return json.dumps(items, ensure_ascii=False, indent=2)


def convert(
    text: str,
    source: str,
    target: str,
    indent_size: int,
    collapse_blank_lines: bool,
    trim_trailing_ws: bool,
    keep_code_fences: bool,
    slack_wrap_codeblock: bool,
    gdocs_bullet_symbol: str,
    convert_smart_quotes: bool,
) -> str:
    text = normalize_text(text, convert_smart_quotes=convert_smart_quotes)

    # Source-specific pre-clean
    if source == "Slack":
        # Slack often flattens indentation; nothing to fix reliably, but normalize bullets
        text = re.sub(r"^[\>]+\s?", "> ", text, flags=re.MULTILINE)  # normalize quotes
    elif source == "Google Docs":
        # Google Docs bullets often come as "•\t" or with odd dashes
        text = text.replace("•\t", "- ")
    elif source in ("Obsidian (Markdown)", "ChatGPT (Markdown)"):
        pass  # already markdown-ish

    blocks: Dict[str, str] = {}
    if keep_code_fences:
        text, blocks = extract_code_fences(text)

    # Line-level transforms
    lines = text.split("\n")

    if target == "Markdown / Obsidian":
        out_lines = lines_to_markdown(lines, indent_size=indent_size, trim_trailing_ws=trim_trailing_ws)
        result = "\n".join(out_lines)
    elif target == "Slack-friendly":
        out_lines = lines_to_markdown(lines, indent_size=indent_size, trim_trailing_ws=trim_trailing_ws)
        result = "\n".join(out_lines)
        if slack_wrap_codeblock:
            result = f"```\n{result}\n```"
    elif target == "Google Docs-friendly":
        out_lines = lines_to_gdocs(lines, indent_size=indent_size, bullet_symbol=gdocs_bullet_symbol, trim_trailing_ws=trim_trailing_ws)
        result = "\n".join(out_lines)
    elif target == "Plain text":
        out_lines = lines_to_plain(lines, indent_size=indent_size, trim_trailing_ws=trim_trailing_ws)
        result = "\n".join(out_lines)
    elif target == "JSON outline (beta)":
        result = to_json_outline(lines, indent_size=indent_size)
    else:
        result = "\n".join(lines)

    if collapse_blank_lines:
        result = re.sub(r"\n{3,}", "\n\n", result)

    if keep_code_fences:
        result = restore_code_fences(result, blocks)

    return result

# ----------------------------
# UI
# ----------------------------
st.title("🧰 インデント変換ツール — Slack / Obsidian / Google Docs / ChatGPT 対応")

with st.sidebar:
    st.header("設定")
    source = st.selectbox(
        "ソース (貼り付け元)",
        ["Auto", "Slack", "Obsidian (Markdown)", "Google Docs", "ChatGPT (Markdown)"]
    )
    target = st.selectbox(
        "ターゲット (出力先)",
        ["Markdown / Obsidian", "Slack-friendly", "Google Docs-friendly", "Plain text", "JSON outline (beta)"]
    )
    indent_size = st.select_slider("インデント幅 (スペース換算)", options=[2, 3, 4, 8], value=2)
    collapse_blank_lines = st.checkbox("空行を 1 行に圧縮", value=True)
    trim_trailing_ws = st.checkbox("行末スペースを削除", value=True)
    keep_code_fences = st.checkbox("``` コードブロックは原文のまま保持", value=True)
    convert_smart_quotes = st.checkbox("スマート引用符をASCIIに正規化", value=True)

    st.divider()
    st.subheader("ターゲット別オプション")
    slack_wrap_codeblock = st.checkbox("Slack: 全文を```でラップしてインデント保護", value=True)
    gdocs_bullet_symbol = st.selectbox("Google Docs: 箇条書きシンボル", ["•", "-"], index=0)

st.caption(
    "貼り付け→設定→変換の3クリックで、体裁崩れやインデント喪失を回避。" 
    "Slack/Docs向けには“見た目が崩れにくい”最適化を行います。"
)

col1, col2 = st.columns(2)
with col1:
    sample = (
        "要件\n"
        "    - Slackのインデントが消える問題\n"
        "        - 対策: ```で囲んで保護\n"
        "    - Google Docsの•問題\n"
        "        1) • がテキストに混在\n"
        "        2) Tabでのネスト判定\n"
        "設計\n"
        "    * 変換ルールの正規化\n"
        "    * コードブロックは保持\n"
        "\n"
        "```sql\nSELECT *\nFROM table -- ここは変更しない\n```\n"
    )
    input_text = st.text_area("貼り付けテキスト", sample, height=360)

with col2:
    if st.button("この設定で変換する", type="primary"):
        output = convert(
            text=input_text,
            source=source,
            target=target,
            indent_size=indent_size,
            collapse_blank_lines=collapse_blank_lines,
            trim_trailing_ws=trim_trailing_ws,
            keep_code_fences=keep_code_fences,
            slack_wrap_codeblock=slack_wrap_codeblock,
            gdocs_bullet_symbol=gdocs_bullet_symbol,
            convert_smart_quotes=convert_smart_quotes,
        )
        st.session_state["converted"] = output

    output = st.session_state.get("converted", "")
    st.text_area("出力", value=output, height=360)
    st.download_button(
        label="converted.txt をダウンロード",
        data=(output or "").encode("utf-8"),
        file_name="converted.txt",
        mime="text/plain",
        disabled=(not output),
    )

with st.expander("変換ルール (要点)", expanded=False):
    st.markdown(
        """
- **空白正規化**: CRLF→LF、NBSP/全角スペース→半角相当、ゼロ幅文字を除去。
- **箇条書き正規化**: `•`, `・`, `–`, `—`, `*`, `-` などを `- ` に統一。`1)`, `1.` などの番号付きも `1.` に統一。
- **インデント推定**: Tabを`インデント幅`相当のスペースに展開し、先頭空白量/Tab数から階層レベルを推定。
- **Markdown出力**: レベル×インデント幅分のスペースを付与し、見栄えを安定化。
- **Slack出力**: 既定で全文を```でラップし、インデントの潰れと自動整形を抑止。
- **Google Docs出力**: レベル回数のTab (`\t`) を付与し、Docsの箇条書き自動認識に寄せる。箇条書きシンボルは `•` または `-` を選択可。
- **コードブロック保持**: ``` で囲まれたブロックは丸ごと非変換で退避→復元。
        """
    )

with st.expander("使い方ヒント", expanded=False):
    st.markdown(
        """
1. **Slackに貼りたい**: ターゲットを *Slack-friendly*、オプションの *全文を```でラップ* をON（推奨）。
2. **Obsidianに整理したい**: ターゲットを *Markdown / Obsidian*。インデント幅は2または4がおすすめ。
3. **Google Docsに貼りたい**: ターゲットを *Google Docs-friendly*。ネストはTabで検出されるため、`•` シンボルが安定。
4. **整列だけしたい**: ターゲットを *Plain text*。改行やインデントのみ整える用途に最適。
5. **構造をデータにしたい**: *JSON outline (beta)* で `level` と `text` の配列を得て、別処理に流用。
        """
    )

st.markdown("---")
st.markdown(
    "Made with ❤️  — インデント崩れにさよなら。"
)
