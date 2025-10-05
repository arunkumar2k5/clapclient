import asyncio
import csv
import io
import json
import os
from typing import Dict, Iterable, List, Optional

import streamlit as st
import websockets

SERVER_URL = os.getenv("MCP_SERVER_URL", "ws://127.0.0.1:8765")

SYSTEM_PROMPT = "Be concise. table format to state the parameters"
MODEL_NAME = "gpt-4o-mini"
TEMPERATURE = 0.2


async def send_llm_request(prompt: str) -> dict:
    async with websockets.connect(SERVER_URL, max_size=2**23) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "initialize",
                    "client": "sample-client",
                    "version": "0.1",
                }
            )
        )
        ready = json.loads(await ws.recv())
        if ready.get("type") != "ready":
            raise RuntimeError(f"Unexpected handshake response: {ready}")

        req = {
            "type": "request",
            "id": "streamlit-compare",
            "method": "llm.generate",
            "params": {
                "prompt": prompt,
                "system": SYSTEM_PROMPT,
                "model": MODEL_NAME,
                "temperature": TEMPERATURE,
                "format": "markdown",
            },
        }
        await ws.send(json.dumps(req))

        resp = json.loads(await ws.recv())
        if resp.get("type") == "result" and resp.get("ok"):
            return resp["data"]
        raise RuntimeError(f"Server error: {resp}")


def build_prompt(items: Iterable[Dict[str, Optional[str]]], source_label: str) -> str:
    comparison_lines = []
    for idx, item in enumerate(items, start=1):
        manufacturer = item.get("manufacturer") or "Unknown manufacturer"
        part_number = item.get("part_number") or "Unknown part number"
        comparison_lines.append(
            f"{idx}. Manufacturer: {manufacturer}; Part number: {part_number}"
        )

    joined_lines = "\n".join(comparison_lines)
    return (
        "You are an electronics expert. Compare the following components for resolution, "
        "interface, supply voltage, environmental considerations, and typical use cases. "
        "Highlight notable trade-offs or suitability for lifecycle assessment.\n\n"
        f"Source: {source_label}\n"
        f"Components:\n{joined_lines}\n\n"
        "Provide a concise table summarizing the comparison followed by key bullet points."
    )


def extract_row_items(row: Dict[str, Optional[str]]) -> List[Dict[str, Optional[str]]]:
    normalized = {
        (key or "").strip().lower(): (value or "").strip() or None
        for key, value in row.items()
    }
    items: List[Dict[str, Optional[str]]] = []

    for idx in range(1, 6):
        base_key = f"manf{idx}"
        manufacturer = normalized.get(base_key)
        part_number = (
            normalized.get(f"{base_key}_partnumber")
            or normalized.get(f"{base_key}_pn")
            or next(
                (
                    normalized[candidate]
                    for candidate in normalized
                    if candidate.startswith(base_key) and "part" in candidate and normalized[candidate]
                ),
                None,
            )
        )

        if manufacturer or part_number:
            items.append({"manufacturer": manufacturer, "part_number": part_number})

    return items


def parse_csv(content: bytes) -> List[Dict[str, object]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, object]] = []

    if reader.fieldnames is None:
        raise ValueError("CSV must include a header row with column names.")

    for row_number, row in enumerate(reader, start=1):
        items = extract_row_items(row)
        if not items:
            continue

        label = row.get("SNO") or row.get("sno") or str(row_number)
        rows.append({"label": str(label).strip() or str(row_number), "items": items, "raw": row})

    return rows


def render_manual_tab() -> None:
    default_a = st.session_state.get("sensor_a", "MLX90393")
    default_b = st.session_state.get("sensor_b", "HMC5883L")

    sensor_a = st.text_input("First sensor part number", value=default_a)
    sensor_b = st.text_input("Second sensor part number", value=default_b)

    result_placeholder = st.empty()

    if st.button("Compare sensors", key="manual_compare"):
        if not sensor_a.strip() or not sensor_b.strip():
            st.warning("Please provide both sensor part numbers before requesting a comparison.")
            return

        st.session_state["sensor_a"] = sensor_a
        st.session_state["sensor_b"] = sensor_b

        prompt = build_prompt(
            [
                {"manufacturer": None, "part_number": sensor_a.strip()},
                {"manufacturer": None, "part_number": sensor_b.strip()},
            ],
            source_label="Manual entry",
        )

        with st.spinner("Contacting MCP server..."):
            try:
                data = asyncio.run(send_llm_request(prompt))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to retrieve comparison: {exc}")
                return

        st.session_state["comparison_result"] = data

    if "comparison_result" in st.session_state:
        data = st.session_state["comparison_result"]
        result_placeholder.markdown(data.get("text", "(No response text provided.)"))
        usage = data.get("usage")
        if usage:
            st.caption(f"Usage: {json.dumps(usage)}")


def render_csv_tab() -> None:
    st.subheader("Batch comparison via CSV upload")
    st.write(
        "Upload a CSV containing columns such as `SNO`, `Manf1`, `Manf1_partnumber`, `Manf2`, "
        "`Manf2_partnumber`, etc. Each row will be processed independently using the MCP server."
    )

    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="csv_uploader")

    if uploaded_file is not None:
        st.caption(f"Selected file: {uploaded_file.name}")

        if st.button("Process CSV", key="process_csv"):
            try:
                rows = parse_csv(uploaded_file.getvalue())
            except Exception as exc:  # noqa: BLE001
                st.error(f"Unable to parse CSV: {exc}")
                return

            if not rows:
                st.warning("No valid component data found in the uploaded CSV.")
                st.session_state.pop("batch_results", None)
                return

            results = []
            with st.spinner(f"Processing {len(rows)} row(s)..."):
                for row in rows:
                    prompt = build_prompt(row["items"], source_label=f"CSV row {row['label']}")
                    try:
                        data = asyncio.run(send_llm_request(prompt))
                    except Exception as exc:  # noqa: BLE001
                        results.append(
                            {
                                "label": row["label"],
                                "items": row["items"],
                                "error": str(exc),
                            }
                        )
                        continue

                    results.append({"label": row["label"], "items": row["items"], "data": data})

            st.session_state["batch_results"] = results

    batch_results = st.session_state.get("batch_results")
    if batch_results:
        st.divider()
        st.subheader("Batch results")
        for result in batch_results:
            header = f"Row {result['label']}"
            with st.expander(header, expanded=False):
                st.markdown(
                    "\n".join(
                        f"- Manufacturer: {item.get('manufacturer') or 'N/A'}, Part number: {item.get('part_number') or 'N/A'}"
                        for item in result["items"]
                    )
                )
                if "error" in result:
                    st.error(result["error"])
                else:
                    data = result["data"]
                    st.markdown(data.get("text", "(No response text provided.)"))
                    usage = data.get("usage")
                    if usage:
                        st.caption(f"Usage: {json.dumps(usage)}")


def main() -> None:
    st.set_page_config(page_title="CLAP", page_icon="🧭")
    st.title("CLAP - component life cycle asssessment platform")
    st.write(
        "Compare one-off components manually or upload a CSV to batch compare manufacturer part numbers via the MCP server."
    )

    manual_tab, csv_tab = st.tabs(["Manual comparison", "CSV batch comparison"])
    with manual_tab:
        render_manual_tab()
    with csv_tab:
        render_csv_tab()


if __name__ == "__main__":
    main()
