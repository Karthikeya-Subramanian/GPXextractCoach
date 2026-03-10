import streamlit as st
import gpxpy
import pandas as pd
import plotly.express as px
import numpy as np

# --- Helper Function: Format decimal minutes to MM:SS ---
def format_time(decimal_minutes):
    if pd.isna(decimal_minutes) or decimal_minutes == float('inf'):
        return "0:00"
    mins = int(decimal_minutes)
    secs = int(round((decimal_minutes - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d}"

# --- Helper Function to Parse GPX ---
@st.cache_data
def parse_gpx(file_bytes):
    gpx = gpxpy.parse(file_bytes)
    data = []
    
    for track in gpx.tracks:
        for segment in track.segments:
            for i, point in enumerate(segment.points):
                row = {
                    'time': point.time,
                    'lat': point.latitude,
                    'lon': point.longitude,
                    'elevation': point.elevation,
                }
                
                # Extract HR and Cadence from extensions if they exist
                for ext in point.extensions:
                    if 'TrackPointExtension' in ext.tag:
                        for child in ext:
                            if 'hr' in child.tag:
                                row['hr'] = int(child.text)
                            if 'cad' in child.tag:
                                row['cad'] = int(child.text)
                                
                if i == 0:
                    row['distance_m'] = 0.0
                    row['time_diff_s'] = 0.0
                else:
                    prev_point = segment.points[i-1]
                    row['distance_m'] = point.distance_2d(prev_point)
                    row['time_diff_s'] = (point.time - prev_point.time).total_seconds()
                    
                data.append(row)
                
    df = pd.DataFrame(data)
    
    # Ensure optional columns exist to prevent KeyErrors
    if 'cad' not in df.columns:
        df['cad'] = np.nan
    if 'hr' not in df.columns:
        df['hr'] = np.nan
        
    df['cum_distance_km'] = df['distance_m'].cumsum() / 1000
    df['cum_time_min'] = df['time_diff_s'].cumsum() / 60
    
    # Calculate speed, smooth over 5 points
    df['speed_m_s'] = df['distance_m'].rolling(5, min_periods=1).sum() / df['time_diff_s'].rolling(5, min_periods=1).sum()
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.fillna(method='bfill', inplace=True)
    
    return df

# --- Main App UI ---
st.set_page_config(page_title="Workout Analyzer", layout="wide")

st.title("GPX Workout Analyzer")
st.markdown("Upload your structured workout data to visualize splits, pace, and heart rate zones.")

uploaded_file = st.file_uploader("Select GPX File", type=["gpx"])

if uploaded_file is not None:
    df = parse_gpx(uploaded_file.getvalue())
    
    st.sidebar.header("Configuration")
    activity_type = st.sidebar.radio("Activity Profile", ["Running", "Cycling"])
    
    if activity_type == "Running":
        df['metric_value'] = 16.666666666667 / df['speed_m_s'] 
        df.loc[df['metric_value'] > 20, 'metric_value'] = 20 # Cap unreasonable paces
        metric_name = "Pace (min/km)"
        if not df['cad'].isna().all():
            df['cad'] = df['cad'] * 2 # Adjust running half-steps
    else:
        df['metric_value'] = df['speed_m_s'] * 3.6
        metric_name = "Speed (km/h)"

    st.sidebar.subheader("Interval Segmentation")
    split_method = st.sidebar.selectbox("Segment Metric", ["Distance (km)", "Time (minutes)"])
    
    placeholder = "3, 6, 3" if split_method == "Distance (km)" else "3, 5, 1, 5, 1, 3"
    splits_input = st.sidebar.text_input("Interval Values (comma separated)", placeholder)
    
    if splits_input:
        try:
            split_lengths = [float(x.strip()) for x in splits_input.split(',')]
            bins = [0] + list(np.cumsum(split_lengths))
            bins.append(float('inf')) 
            
            labels = [f"Split {i+1} ({val})" for i, val in enumerate(split_lengths)] + ["Remaining"]
            target_col = 'cum_distance_km' if split_method == "Distance (km)" else 'cum_time_min'
            
            df['Segment'] = pd.cut(df[target_col], bins=bins, labels=labels, right=True)
            df = df[df['Segment'].notna()]
            
            has_hr = not df['hr'].isna().all()
            has_cad = not df['cad'].isna().all()
            
            # --- Workout Summary Table ---
            st.markdown("### Overview")
            
            agg_dict = {
                'distance_m': lambda x: x.sum() / 1000,
                'time_diff_s': lambda x: x.sum() / 60,
                'metric_value': 'mean'
            }
            if has_hr: agg_dict['hr'] = 'mean'
            if has_cad: agg_dict['cad'] = 'mean'
            
            summary = df.groupby('Segment', observed=True).agg(agg_dict).reset_index()
            summary.rename(columns={'distance_m': 'Distance (km)', 'time_diff_s': 'Time_min', 'metric_value': f'Avg {metric_name}', 'hr': 'Avg HR', 'cad': 'Avg Cadence'}, inplace=True)
            
            # Formatting for display
            display_summary = summary.copy()
            display_summary['Time'] = display_summary['Time_min'].apply(format_time)
            
            if activity_type == "Running":
                display_summary[f'Avg {metric_name}'] = display_summary[f'Avg {metric_name}'].apply(format_time)
            else:
                display_summary[f'Avg {metric_name}'] = display_summary[f'Avg {metric_name}'].round(2)
            
            display_cols = ['Segment', 'Distance (km)', 'Time', f'Avg {metric_name}']
            format_dict = {'Distance (km)': '{:.2f}'}
            
            if has_hr:
                display_cols.append('Avg HR')
                format_dict['Avg HR'] = '{:.0f}'
            if has_cad:
                display_cols.append('Avg Cadence')
                format_dict['Avg Cadence'] = '{:.0f}'
                
            st.dataframe(display_summary[display_cols].style.format(format_dict))
            
            # --- Sub-Segment Detailed Splits ---
            st.markdown("### Lap Details")
            
            for segment_name in df['Segment'].dropna().unique():
                seg_df = df[df['Segment'] == segment_name].copy()
                if seg_df.empty or segment_name == "Remaining": 
                    continue
                
                with st.expander(f"Expand {segment_name} (1 {split_method.split(' ')[0]} laps)"):
                    seg_df['local_cum'] = seg_df[target_col] - seg_df[target_col].iloc[0]
                    max_local = seg_df['local_cum'].max()
                    
                    sub_bins = list(range(0, int(np.ceil(max_local)) + 1))
                    if len(sub_bins) == 1: sub_bins.append(1) 
                    
                    sub_labels = [f"Lap {i+1}" for i in range(len(sub_bins)-1)]
                    seg_df['Sub_Segment'] = pd.cut(seg_df['local_cum'], bins=sub_bins, labels=sub_labels, right=True)
                    
                    sub_summary = seg_df.groupby('Sub_Segment', observed=True).agg(agg_dict).reset_index()
                    sub_summary.rename(columns={'distance_m': 'Distance (km)', 'time_diff_s': 'Time_min', 'metric_value': f'Avg {metric_name}', 'hr': 'Avg HR', 'cad': 'Avg Cadence'}, inplace=True)
                    
                    sub_summary['Time'] = sub_summary['Time_min'].apply(format_time)
                    if activity_type == "Running":
                        sub_summary[f'Avg {metric_name}'] = sub_summary[f'Avg {metric_name}'].apply(format_time)
                    else:
                        sub_summary[f'Avg {metric_name}'] = sub_summary[f'Avg {metric_name}'].round(2)
                        
                    st.dataframe(sub_summary[['Sub_Segment'] + [c for c in display_cols if c != 'Segment']].style.format(format_dict))

            # --- Visualizations ---
            st.markdown("### Telemetry")
            
            if has_hr:
                fig_hr = px.scatter(
                    df, x=target_col, y='hr', color='Segment',
                    labels={target_col: split_method, 'hr': 'Heart Rate (bpm)'}
                )
                fig_hr.update_traces(mode='lines+markers', marker=dict(size=4))
                fig_hr.update_layout(title="Heart Rate Profile", margin=dict(t=40, b=0, l=0, r=0))
                st.plotly_chart(fig_hr, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                fig_metric = px.line(
                    df, x=target_col, y='metric_value', color='Segment',
                    labels={target_col: split_method, 'metric_value': metric_name}
                )
                fig_metric.update_layout(title=f"{metric_name.split(' ')[0]} Profile", margin=dict(t=40, b=0, l=0, r=0))
                if activity_type == "Running":
                    fig_metric.update_yaxes(autorange="reversed") 
                st.plotly_chart(fig_metric, use_container_width=True)
                
            with col2:
                if has_cad:
                    fig_cad = px.line(
                        df, x=target_col, y='cad', color='Segment',
                        labels={target_col: split_method, 'cad': 'Cadence'}
                    )
                    fig_cad.update_layout(title="Cadence Profile", margin=dict(t=40, b=0, l=0, r=0))
                    st.plotly_chart(fig_cad, use_container_width=True)
                else:
                    st.info("No cadence data available in this file.")

        except Exception as e:
            st.error("Data processing error. Please verify your interval inputs.")