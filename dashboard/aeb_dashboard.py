import streamlit as st
import boto3
import pandas as pd
import json
import tarfile
import io
import plotly.express as px
import plotly.graph_objects as go
import os
import re
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURATION ---
BUCKET_NAME = "carla-simulation-results-2601"
S3_PREFIX = "regressions"

st.set_page_config(page_title="AEB Live Dashboard", layout="wide")
# Auto-refresh the page every 30 seconds
st_autorefresh(interval=30000, limit=200, key="refresh_counter")

st.title("🚗 AEB Test Analytics (Live)")
st.caption("Data is fetched in real-time from AWS S3. Select a regression to inspect all runs.")

# --- Cache the S3 client ---
@st.cache_resource
def get_s3_client():
    return boto3.client('s3')

# --- List regression IDs detected in bucket ---
@st.cache_data(ttl=30)
def list_regressions():
    s3 = get_s3_client()
    keys = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=S3_PREFIX + '/'):
            for obj in page.get('Contents', []):
                keys.append(obj['Key'])
    except Exception:
        return []

    reg_ids = set()
    pattern = re.compile(r'regression_(\d{8}_\d{6})')
    for k in keys:
        m = pattern.search(k)
        if m:
            reg_ids.add(m.group(1))
    return sorted(list(reg_ids), reverse=True)

@st.cache_data(ttl=60)
def list_keys_for_regression(reg_id):
    s3 = get_s3_client()
    prefix = f"{S3_PREFIX}/{reg_id}/"
    keys = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
            for obj in page.get('Contents', []):
                keys.append(obj['Key'])
    except Exception:
        # fallback: try global listing for matching reg_id
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        for obj in response.get('Contents', []):
            if f'regression_{reg_id}' in obj['Key']:
                keys.append(obj['Key'])
    return keys

# Load all metrics.json entries out of a combined tar (or multiple per-test tars)
@st.cache_data(ttl=60)
def load_regression_metrics(reg_id):
    s3 = get_s3_client()
    keys = list_keys_for_regression(reg_id)
    # Prefer combined tar key
    combined_key = None
    for k in keys:
        if k.endswith(f"regression_{reg_id}.tar.gz"):
            combined_key = k
            break

    runs = []  # list of dicts: {name, df, summary}

    def process_tar_bytes(bytes_io, source_name="combined"):
        try:
            with tarfile.open(fileobj=io.BytesIO(bytes_io), mode='r:gz') as tar:
                for member in tar.getmembers():
                    if member.name.endswith('metrics.json'):
                        try:
                            f = tar.extractfile(member)
                            if f is None:
                                continue
                            metrics = json.load(f)
                            df = pd.DataFrame(metrics)
                            # run name: parent folder of metrics.json
                            run_name = os.path.basename(os.path.dirname(member.name)) or source_name
                            runs.append({'name': run_name, 'df': df})
                        except Exception:
                            continue
        except Exception:
            return

    if combined_key:
        try:
            obj = s3.get_object(Bucket=BUCKET_NAME, Key=combined_key)
            bytes_io = obj['Body'].read()
            process_tar_bytes(bytes_io, source_name=combined_key)
        except Exception:
            pass
    else:
        # Process all per-test tars
        for k in keys:
            if k.endswith('.tar.gz'):
                try:
                    obj = s3.get_object(Bucket=BUCKET_NAME, Key=k)
                    bytes_io = obj['Body'].read()
                    process_tar_bytes(bytes_io, source_name=k)
                except Exception:
                    continue

    # Build summary for each run
    summaries = []
    for item in runs:
        df = item['df']
        name = item['name']
        if df.empty:
            summaries.append({'name': name, 'min_ttc': None, 'min_distance': None, 'max_speed': None, 'collision': None, 'pass': None})
            continue
        # Normalize column presence
        ttc = df['ttc'] if 'ttc' in df.columns else pd.Series(dtype=float)
        dist = df['distance_to_adversary'] if 'distance_to_adversary' in df.columns else pd.Series(dtype=float)
        speed = df['ego_speed'] if 'ego_speed' in df.columns else pd.Series(dtype=float)

        # min ttc (ignore None/NaN)
        ttc_vals = pd.to_numeric(ttc, errors='coerce').dropna()
        min_ttc = float(ttc_vals.min()) if not ttc_vals.empty else None

        dist_vals = pd.to_numeric(dist, errors='coerce').dropna()
        min_dist = float(dist_vals.min()) if not dist_vals.empty else None

        speed_vals = pd.to_numeric(speed, errors='coerce').dropna()
        max_speed = float(speed_vals.max()) if not speed_vals.empty else None

        # collision detection if 'collision' exists
        collision = None
        if 'collision' in df.columns:
            try:
                collision = bool(df['collision'].astype(bool).any())
            except Exception:
                collision = None

        # pass/fail logic: pass if no collision and min_ttc >= 1.5
        passed = None
        if collision is not None and min_ttc is not None:
            passed = (not collision) and (min_ttc >= 1.5)
        else:
            # if we don't have enough info, mark None
            passed = None

        summaries.append({'name': name, 'min_ttc': min_ttc, 'min_distance': min_dist, 'max_speed': max_speed, 'collision': collision, 'pass': passed})

    return runs, pd.DataFrame(summaries)


# --- UI Flow ---
regressions = list_regressions()
if not regressions:
    st.info("S3 Bucket is empty or no regressions found.")
    st.stop()

selected_reg = st.sidebar.selectbox("Select Regression (by ID):", regressions, index=0)
with st.spinner('Loading regression data...'):
    runs, summary_df = load_regression_metrics(selected_reg)

if summary_df.empty:
    st.error("No runs or metrics.json files found in the selected regression.")
    st.stop()

# Regression level pass/fail
num_runs = len(summary_df)
num_pass = int(summary_df['pass'].sum() if 'pass' in summary_df.columns else 0)
num_fail = int(((summary_df['pass'] == False).sum()) if 'pass' in summary_df.columns else 0)
reg_status = "PASS" if num_runs>0 and num_pass == num_runs else "FAIL"

c1, c2, c3 = st.columns(3)
c1.metric("Regression ID", selected_reg)
c2.metric("Status", reg_status)
c3.metric("Pass/Fail", f"{num_pass}/{num_runs}")

st.subheader("Run Summaries")
st.dataframe(summary_df.sort_values(by=['name']))

# Plotting
metric_choice = st.selectbox('Metric to plot', options=['ttc', 'distance_to_adversary', 'ego_speed'], index=0)

fig = go.Figure()
colors = {True: 'green', False: 'red', None: 'gray'}
for r in runs:
    name = r['name']
    df = r['df']
    if metric_choice not in df.columns:
        continue
    y = pd.to_numeric(df[metric_choice], errors='coerce')
    x = df['frame'] if 'frame' in df.columns else range(len(y))
    # find pass for this run
    srow = summary_df[summary_df['name'] == name]
    pass_val = None
    if not srow.empty and 'pass' in srow.columns:
        pass_val = srow.iloc[0]['pass']
    fig.add_trace(go.Scatter(x=x, y=y, mode='lines+markers', name=f"{name} ({'PASS' if pass_val else 'FAIL' if pass_val==False else 'N/A'})", line=dict(color=colors[pass_val])))

fig.update_layout(title=f"Regression {selected_reg} - {metric_choice}", xaxis_title='frame', yaxis_title=metric_choice)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption("Pass criteria: no collision && min TTC >= 1.5 s (if metrics available).")

# Allow download of combined tar if present
s3 = get_s3_client()
combined_key = f"{S3_PREFIX}/{selected_reg}/regression_{selected_reg}.tar.gz"
try:
    s3.head_object(Bucket=BUCKET_NAME, Key=combined_key)
    if st.button('Download combined regression tar'):
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=combined_key)
        st.download_button(label='Download TAR', data=obj['Body'].read(), file_name=f'regression_{selected_reg}.tar.gz')
except Exception:
    st.info('Combined regression tar not found in S3. Individual per-test tars may be available.')
