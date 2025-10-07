import streamlit as st
import csv
import io
import json
import asyncio
import os
import pandas as pd
import websockets
from digikeyjson import fetch_digikey_data

SERVER_URL = os.getenv("MCP_SERVER_URL", "ws://127.0.0.1:8765")
SYSTEM_PROMPT = "You are an electronics expert. Compare the following components and provide a concise table format to state the parameters, highlighting key differences."
MODEL_NAME = "gpt-4o-mini"
TEMPERATURE = 0.2

async def send_json_to_llm(json_content: list, json_filename: str) -> dict:
    """Send JSON content to MCP server and get LLM analysis for replacement justification."""
    async with websockets.connect(SERVER_URL, max_size=2**23) as ws:
        await ws.send(json.dumps({
            "type": "initialize",
            "client": "streamlit-client",
            "version": "0.1"
        }))
        ready = json.loads(await ws.recv())
        if ready.get("type") != "ready":
            raise RuntimeError(f"Unexpected handshake response: {ready}")
        
        # Build prompt with reference component (first one)
        reference_part = json_content[0].get("Part Number", "Reference") if json_content else "Reference"
        prompt = f"""Analyze the following electronic components for replacement compatibility. 
The FIRST component '{reference_part}' is the REFERENCE component.

Components data:
{json.dumps(json_content, indent=2)}

For each parameter, provide a justification whether the alternative components are suitable replacements for the reference component.
Focus on: electrical compatibility, mechanical compatibility, lifecycle status, and any critical differences.
Be concise but specific about compatibility concerns."""
        
        req = {
            "type": "request",
            "id": f"analyze-{json_filename}",
            "method": "llm.generate",
            "params": {
                "prompt": prompt,
                "system": SYSTEM_PROMPT,
                "model": MODEL_NAME,
                "temperature": TEMPERATURE,
                "format": "markdown"
            }
        }
        await ws.send(json.dumps(req))
        resp = json.loads(await ws.recv())
        if resp.get("type") == "result" and resp.get("ok"):
            return resp["data"]
        raise RuntimeError(f"Server error: {resp}")

st.set_page_config(page_title="Digikey Batch JSON Downloader", page_icon="🔗")
st.title("Digikey Batch Part Data Downloader & Analyzer")
st.write("Upload a CSV with columns Manf1_partno, Manf2_partno, Manf3_partno, Manf4_partno. Each row will be processed, analyzed by LLM, and saved to Excel.")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if uploaded_file is not None:
    st.caption(f"Selected file: {uploaded_file.name}")
    if st.button("Process CSV"):
        try:
            text = uploaded_file.getvalue().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows_data = []
            for row in reader:
                part_numbers = []
                for col in ['Manf1_partno', 'Manf2_partno', 'Manf3_partno', 'Manf4_partno']:
                    pn = row.get(col, '').strip()
                    if pn:
                        part_numbers.append(pn)
                if part_numbers:
                    output_name = part_numbers[0]
                    rows_data.append((part_numbers, output_name))
        except Exception as exc:
            st.error(f"Unable to parse CSV: {exc}")
            rows_data = []
        if not rows_data:
            st.warning("No valid part numbers found in the uploaded CSV.")
        else:
            st.info(f"Found {len(rows_data)} row(s) to process. Fetching from Digikey...")
            json_files = []
            for part_numbers, output_name in rows_data:
                try:
                    filename = fetch_digikey_data(part_numbers, output_name)
                    json_files.append(filename)
                    st.success(f"Saved {filename} with {len(part_numbers)} part(s)")
                except Exception as exc:
                    st.error(f"{output_name}: {exc}")
            
            if json_files:
                st.info("Sending JSON files to LLM server for analysis...")
                excel_data = {}
                for fname in json_files:
                    try:
                        with open(fname, "r") as f:
                            json_content = json.load(f)
                        
                        # Create parameter comparison table
                        if not json_content:
                            st.warning(f"No data in {fname}")
                            continue
                        
                        # Get all unique parameters
                        all_params = set()
                        for component in json_content:
                            all_params.update(component.keys())
                        all_params = sorted(all_params)
                        
                        # Build dataframe with parameters as rows
                        data = {"Parameter": all_params}
                        for idx, component in enumerate(json_content):
                            part_num = component.get("Part Number", f"Component {idx+1}")
                            data[part_num] = [component.get(param, "-") for param in all_params]
                        
                        # Get LLM justification
                        llm_response = asyncio.run(send_json_to_llm(json_content, fname))
                        justification_text = llm_response.get("text", "No analysis available")
                        
                        # Add justification column (same text for all rows for now)
                        data["Replacement Justification"] = [justification_text] * len(all_params)
                        
                        df = pd.DataFrame(data)
                        sheet_name = fname.replace(".json", "")[:31]
                        excel_data[sheet_name] = df
                        st.success(f"Analyzed {fname}")
                    except Exception as exc:
                        st.error(f"Error analyzing {fname}: {exc}")
                
                if excel_data:
                    output_excel = "analysis_results.xlsx"
                    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                        for sheet_name, df in excel_data.items():
                            df.to_excel(writer, sheet_name=sheet_name, index=False)
                    st.success(f"Created Excel file: {output_excel}")
                    with open(output_excel, "rb") as f:
                        st.download_button(
                            label="Download Analysis Excel",
                            data=f,
                            file_name=output_excel,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                
                st.subheader("Download Individual JSON files:")
                for fname in json_files:
                    with open(fname, "rb") as f:
                        st.download_button(
                            label=f"Download {fname}",
                            data=f,
                            file_name=fname,
                            mime="application/json",
                            key=f"json_{fname}"
                        )
