import streamlit as st
import gpxpy
import pandas as pd
import plotly.express as px
import numpy as np
from fpdf import FPDF

# Must be called first
st.set_page_config(page_title="Workout Analyzer", layout="wide")

# --- Helper Function: Format decimal minutes to MM:SS ---
def format_time(decimal_minutes):
    if pd.isna(decimal_minutes) or decimal_minutes == float('inf') or decimal_minutes < 0:
        return "0:00"
    mins = int(decimal_minutes)
    secs = int(round((decimal_minutes - mins) * 60))
    if secs >= 60:
        mins += 1
        secs -= 60
    return f"{mins}:{secs:02d}"

# --- Helper Function: Generate PDF Report ---
def generate_pdf_report(activity_type, summary_df, detailed_dfs):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, f'GPX {activity_type} Workout Report', 0, 1, 'C')
            self.ln(5)

    pdf = PDF()
    pdf.add_page()
    
    def add_table_to_pdf(df, title):
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, title, 0, 1)
        pdf.set_font('Arial', 'B', 8)
        
        epw = pdf.w - 2 * pdf.l_margin
        col_width = epw / len(df.columns)
        row_height = 8
        
        for col in df.columns:
            pdf.cell(col_width, row_height, str(col), border=1, align='C')
        pdf.ln()
        
        pdf.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            for item in row:
                pdf.cell(col_width, row_height, str(item), border=1, align='C')
            pdf.ln()
        pdf.ln(5)

    add_table_to_pdf(summary_df, "Overall Workout Summary")
    for segment_name, sub_df in detailed_dfs.items():
        add_table_to_pdf(sub_df, f"Lap Details: {segment_name}")
        
    return pdf.output(dest='S').encode('latin-1')

# --- Helper Function to Parse GPX ---
@st.cache_data
def parse_gpx(file_bytes):
    gpx = gpxpy.parse(file_bytes)
    data = []
    
    for track in gpx.tracks:
        for segment in track.segments:
            for i, point in enumerate(segment.points):
                row = {
                    'lat': point.latitude,
                    'lon': point.longitude,
                    'elevation': point.elevation if point.elevation is not None else 0.0,
                }
                
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
                    
                    if point.time is not None and prev_point.time is not None:
                        row['time_diff_s'] = (point.time - prev_point.time).total_seconds()
                    else:
                        row['time_diff_s'] = 0.0
                        
                data.append(row)
                
    df = pd.DataFrame(data)
    
    df['ele_diff'] = df['elevation'].diff().fillna(0)
    df['ele_gain'] = df['ele_diff'].clip(lower=0)
    
    if 'cad' not in df.columns: df['cad'] = np.nan
    if 'hr' not in df.columns: df['hr'] = np.nan
        
    df['cum_distance_km'] = df['distance_m'].cumsum() / 1000
    df['cum_time_min'] = df['time_diff_s'].cumsum() / 60
    
    sum_dist = df['distance_m'].rolling(5, min_periods=1).sum()
    sum_time = df['time_diff_s'].rolling(5, min_periods=1).sum()
    df['speed_m_s'] = np.where(sum_time > 0, sum_dist / sum_time, 0.0)
    
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.bfill(inplace=True)
    
    return df

# --- Main App UI ---
st.title("GPX Workout Analyzer")
st.markdown("Upload your structured workout data to visualize splits, pace, heart rate, and power/elevation metrics.")

uploaded_file = st.file_uploader("Select GPX File", type=["gpx"])

if uploaded_file is not None:
    df = parse_gpx(uploaded_file.getvalue())
    is_route = df['time_diff_s'].sum() == 0
    
    st.sidebar.header("Configuration")
    activity_type = st.sidebar.radio("Activity Profile", ["Running", "Cycling"])
    
    st.sidebar.subheader("Athlete Profile")
    user_weight = st.sidebar.number_input("Body Weight (kg)", value=61.0, step=1.0)
    
    if is_route:
        st.sidebar.markdown("---")
        st.warning("🗺️ **Planning Mode Active:** This file is a Route and lacks timestamps. Enter your target pace/speed below to generate estimated split times and power output.")
        
        if activity_type == "Running":
            target_pace = st.sidebar.number_input("Target Pace (min/km)", value=4.00, step=0.1)
            target_speed_m_s = 1000 / (target_pace * 60)
        else:
            target_speed_kmh = st.sidebar.number_input("Target Speed (km/h)", value=30.0, step=1.0)
            target_speed_m_s = target_speed_kmh / 3.6
            
        df['time_diff_s'] = np.where(df['distance_m'] > 0, df['distance_m'] / target_speed_m_s, 0.0)
        df['cum_time_min'] = df['time_diff_s'].cumsum() / 60
        df['speed_m_s'] = np.where(df['distance_m'] > 0, target_speed_m_s, 0.0)
    
    # --- METRICS LOGIC ---
    if activity_type == "Running":
        df['metric_value'] = np.where(df['speed_m_s'] > 0, 16.666666666667 / df['speed_m_s'], 0.0)
        df.loc[df['metric_value'] > 20, 'metric_value'] = 20 
        metric_name = "Pace (min/km)"
        
        if not df['cad'].isna().all():
            df['cad'] = df['cad'] * 2 
            df['stride_length_m'] = np.where(df['cad'] > 0, (df['speed_m_s'] * 60) / df['cad'], 0)
            
    else: 
        df['metric_value'] = df['speed_m_s'] * 3.6
        metric_name = "Speed (km/h)"
        
        st.sidebar.subheader("Equipment (Cycling)")
        bike_weight = st.sidebar.number_input("Bike Weight (kg)", value=17.0, step=0.5)
        total_mass = user_weight + bike_weight
        
        Crr = st.sidebar.number_input("Rolling Resistance (Crr)", value=0.008, format="%.3f")
        CdA = st.sidebar.number_input("Aero Drag (CdA)", value=0.38, format="%.2f")
        rho = st.sidebar.number_input("Air Density (kg/m^3)", value=1.11, format="%.2f")
        
        g = 9.81
        grade_decimal = df['ele_diff'] / df['distance_m']
        grade_decimal = grade_decimal.replace([np.inf, -np.inf], 0).fillna(0)
        v = df['speed_m_s']
        
        F_gravity = total_mass * g * grade_decimal
        F_rolling = total_mass * g * Crr
        F_drag = 0.5 * rho * CdA * (v ** 2)
        raw_power = (F_gravity + F_rolling + F_drag) * v
        df['watts'] = raw_power.clip(lower=0)

    st.sidebar.subheader("Interval Segmentation")
    split_method = st.sidebar.selectbox("Segment Metric", ["Distance (km)", "Time (minutes)"])
    placeholder = "10" if split_method == "Distance (km)" else "3, 5, 1, 5, 1, 3"
    splits_input = st.sidebar.text_input("Major Intervals (comma separated, use 'x' for repeats)", placeholder)
    
    sub_lap_size = st.sidebar.number_input(
        f"Lap Details Resolution ({split_method.split(' ')[0]})", 
        value=0.4 if split_method == "Distance (km)" else 1.0, step=0.1, min_value=0.05
    )
    
    if splits_input:
        try:
            split_lengths = []
            for x in splits_input.split(','):
                x = x.strip()
                if not x: continue
                if 'x' in x.lower():
                    count_str, val_str = x.lower().split('x')
                    split_lengths.extend([float(val_str.strip())] * int(count_str.strip()))
                else:
                    split_lengths.append(float(x))
                    
            bins = [0] + list(np.cumsum(split_lengths))
            bins.append(float('inf')) 
            
            labels = [f"Split {i+1} ({val})" for i, val in enumerate(split_lengths)] + ["Remaining"]
            target_col = 'cum_distance_km' if split_method == "Distance (km)" else 'cum_time_min'
            
            df['Segment'] = pd.cut(df[target_col], bins=bins, labels=labels, right=True, include_lowest=True)
            df = df[df['Segment'].notna()]
            
            has_hr = not df['hr'].isna().all()
            has_cad = not df['cad'].isna().all()
            has_stride = 'stride_length_m' in df.columns
            has_watts = 'watts' in df.columns
            
            # --- OVERALL STATS CALCULATIONS ---
            total_dist = df['distance_m'].sum() / 1000
            total_time = df['time_diff_s'].sum() / 60
            
            # Calorie Calculation
            if activity_type == "Running":
                total_calories = user_weight * total_dist * 1.036
            else:
                if has_watts:
                    total_joules = (df['watts'] * df['time_diff_s']).sum()
                    total_calories = total_joules / 1000
                else:
                    total_calories = 10.0 * user_weight * (total_time / 60)
            
            # --- TOP METRICS DASHBOARD ---
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Distance", f"{total_dist:.2f} km")
            col2.metric("Total Time", format_time(total_time))
            col3.metric("Calories Burned", f"{int(total_calories)} kcal")
            st.markdown("---")

            # --- GPS ROUTE MAP (THIN & COLOR CODED) ---
            st.markdown("### GPS Route")
            valid_coords = df.dropna(subset=['lat', 'lon']).copy()
            if not valid_coords.empty:
                if activity_type == "Running":
                    valid_coords['color_metric'] = valid_coords['metric_value'].clip(upper=10)
                    color_scale = 'Viridis_r'
                else:
                    valid_coords['color_metric'] = valid_coords['metric_value']
                    color_scale = 'Viridis'

                fig_map = px.scatter_mapbox(
                    valid_coords, 
                    lat="lat", lon="lon", 
                    color='color_metric',
                    color_continuous_scale=color_scale,
                    zoom=13,
                    mapbox_style="carto-positron",
                    labels={'color_metric': metric_name}
                )
                fig_map.update_traces(marker=dict(size=2, opacity=0.8))
                fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                st.plotly_chart(fig_map, width='stretch')


            agg_dict = {
                'distance_m': lambda x: x.sum() / 1000,
                'time_diff_s': lambda x: x.sum() / 60,
                'ele_gain': 'sum',
                'ele_diff': 'sum'
            }
            if has_hr: agg_dict['hr'] = 'mean'
            if has_cad: agg_dict['cad'] = 'mean'
            if has_stride: agg_dict['stride_length_m'] = 'mean'
            if has_watts: agg_dict['watts'] = 'mean'
            
            # --- Workout Summary Table ---
            st.markdown("### Overview")
            
            summary = df.groupby('Segment', observed=True).agg(agg_dict).reset_index()
            summary.rename(columns={'distance_m': 'Distance (km)', 'time_diff_s': 'Time_min'}, inplace=True)
            
            if activity_type == "Running":
                summary[f'Avg {metric_name}'] = np.where(summary['Distance (km)'] > 0, summary['Time_min'] / summary['Distance (km)'], 0.0)
            else:
                summary[f'Avg {metric_name}'] = np.where(summary['Time_min'] > 0, summary['Distance (km)'] / (summary['Time_min'] / 60), 0.0)
                
            summary['Gradient (%)'] = np.where(summary['Distance (km)'] > 0, 
                                              (summary['ele_diff'] / (summary['Distance (km)'] * 1000)) * 100, 0)
            summary['Elev Gain (m)'] = summary['ele_gain']
            
            raw_metric_col = f'Avg {metric_name} (Raw)'
            display_summary = summary.copy()
            display_summary[raw_metric_col] = display_summary[f'Avg {metric_name}']
            
            display_summary['Time'] = display_summary['Time_min'].apply(format_time)
            display_summary['Distance (km)'] = display_summary['Distance (km)'].map('{:.2f}'.format)
            display_summary['Elev Gain (m)'] = display_summary['Elev Gain (m)'].map('{:.2f}'.format)
            display_summary['Gradient (%)'] = summary['Gradient (%)'].map('{:.2f}'.format) + '%'
            
            if activity_type == "Running":
                display_summary[f'Avg {metric_name}'] = display_summary[f'Avg {metric_name}'].apply(format_time)
            else:
                display_summary[f'Avg {metric_name}'] = summary[f'Avg {metric_name}'].map('{:.2f}'.format)
            
            display_cols = ['Segment', 'Distance (km)', 'Time', f'Avg {metric_name}', 'Elev Gain (m)', 'Gradient (%)']
            
            if has_hr:
                display_summary['Avg HR'] = summary['hr'].map('{:.0f}'.format)
                display_cols.append('Avg HR')
            if has_cad:
                display_summary['Avg Cadence'] = summary['cad'].map('{:.0f}'.format)
                display_cols.append('Avg Cadence')
            if has_stride:
                display_summary['Avg Stride (m)'] = summary['stride_length_m'].map('{:.2f}'.format)
                display_cols.append('Avg Stride (m)')
            if has_watts:
                display_summary['Avg Power (W)'] = summary['watts'].map('{:.0f}'.format)
                display_cols.append('Avg Power (W)')
                
            cmap = 'Greens_r' if activity_type == "Running" else 'Greens'
            styled_summary = display_summary[display_cols + [raw_metric_col]].style.background_gradient(
                subset=[raw_metric_col], cmap=cmap
            ).hide(axis="columns", subset=[raw_metric_col])
            
            st.dataframe(styled_summary)
            
            # --- Split Visualization Bar Chart ---
            y_col = 'Time_min' if split_method == "Distance (km)" else 'Distance (km)'
            y_label = "Time (Minutes)" if split_method == "Distance (km)" else "Distance (km)"
            bar_text = display_summary['Time'] if split_method == "Distance (km)" else display_summary['Distance (km)'] + ' km'
            
            fig_bar = px.bar(
                summary, 
                x='Segment', 
                y=y_col,
                color=f'Avg {metric_name}',
                text=bar_text,
                title=f"Workout Structure ({y_label} per Split)",
                color_continuous_scale=px.colors.sequential.Viridis
            )
            
            if activity_type == "Running":
                fig_bar.update_coloraxes(reversescale=True)

            fig_bar.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(fig_bar, width='stretch')

            # --- Sub-Segment Detailed Splits ---
            st.markdown("### Lap Details")
            pdf_detailed_dfs = {}
            
            for segment_name in df['Segment'].dropna().unique():
                seg_df = df[df['Segment'] == segment_name].copy()
                if seg_df.empty or segment_name == "Remaining": 
                    continue
                
                with st.expander(f"Expand {segment_name} ({sub_lap_size} {split_method.split(' ')[0]} laps)"):
                    seg_df['local_cum'] = seg_df[target_col] - seg_df[target_col].iloc[0]
                    max_local = seg_df['local_cum'].max()
                    
                    num_laps = int(np.ceil(max_local / sub_lap_size))
                    if num_laps == 0: num_laps = 1
                    
                    sub_bins = [i * sub_lap_size for i in range(num_laps + 1)]
                    sub_bins[-1] = max(sub_bins[-1], max_local + 1.0) 
                    
                    sub_labels = [f"Lap {i+1}" for i in range(len(sub_bins)-1)]
                    seg_df['Sub_Segment'] = pd.cut(seg_df['local_cum'], bins=sub_bins, labels=sub_labels, right=True, include_lowest=True)
                    
                    sub_summary = seg_df.groupby('Sub_Segment', observed=True).agg(agg_dict).reset_index()
                    sub_summary.rename(columns={'distance_m': 'Distance (km)', 'time_diff_s': 'Time_min'}, inplace=True)
                    
                    if activity_type == "Running":
                        sub_summary[f'Avg {metric_name}'] = np.where(sub_summary['Distance (km)'] > 0, sub_summary['Time_min'] / sub_summary['Distance (km)'], 0.0)
                    else:
                        sub_summary[f'Avg {metric_name}'] = np.where(sub_summary['Time_min'] > 0, sub_summary['Distance (km)'] / (sub_summary['Time_min'] / 60), 0.0)
                    
                    sub_summary['Gradient (%)'] = np.where(sub_summary['Distance (km)'] > 0, 
                                                          (sub_summary['ele_diff'] / (sub_summary['Distance (km)'] * 1000)) * 100, 0)
                    sub_summary['Elev Gain (m)'] = sub_summary['ele_gain']
                    
                    sub_summary[raw_metric_col] = sub_summary[f'Avg {metric_name}']

                    sub_summary['Time'] = sub_summary['Time_min'].apply(format_time)
                    sub_summary['Distance (km)'] = sub_summary['Distance (km)'].map('{:.2f}'.format)
                    sub_summary['Elev Gain (m)'] = sub_summary['Elev Gain (m)'].map('{:.2f}'.format)
                    sub_summary['Gradient (%)'] = sub_summary['Gradient (%)'].map('{:.2f}'.format) + '%'
                    
                    if activity_type == "Running":
                        sub_summary[f'Avg {metric_name}'] = sub_summary[f'Avg {metric_name}'].apply(format_time)
                    else:
                        sub_summary[f'Avg {metric_name}'] = sub_summary[f'Avg {metric_name}'].map('{:.2f}'.format)
                        
                    if has_hr:
                        sub_summary['Avg HR'] = sub_summary['hr'].map('{:.0f}'.format)
                    if has_cad:
                        sub_summary['Avg Cadence'] = sub_summary['cad'].map('{:.0f}'.format)
                    if has_stride:
                        sub_summary['Avg Stride (m)'] = sub_summary['stride_length_m'].map('{:.2f}'.format)
                    if has_watts:
                        sub_summary['Avg Power (W)'] = sub_summary['watts'].map('{:.0f}'.format)
                        
                    final_sub_df = sub_summary[['Sub_Segment'] + [c for c in display_cols if c != 'Segment']]
                    
                    styled_sub_df = sub_summary[['Sub_Segment'] + [c for c in display_cols if c != 'Segment'] + [raw_metric_col]].style.background_gradient(
                        subset=[raw_metric_col], cmap=cmap
                    ).hide(axis="columns", subset=[raw_metric_col])
                    
                    st.dataframe(styled_sub_df)
                    pdf_detailed_dfs[segment_name] = final_sub_df

            # --- PDF Download Button ---
            st.markdown("---")
            pdf_bytes = generate_pdf_report(activity_type, display_summary[display_cols], pdf_detailed_dfs)
            
            # Extract the original file name and swap the extension
            original_name = uploaded_file.name.rsplit('.', 1)[0]
            pdf_filename = f"{original_name}_report.pdf"
            
            st.download_button(
                label="📄 Download Report as PDF",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf"
            )
            st.markdown("---")

            # --- Visualizations ---
            st.markdown("### Telemetry")
            
            if has_hr:
                # Standard HR Line Chart
                fig_hr = px.scatter(
                    df, x=target_col, y='hr', color='Segment',
                    labels={target_col: split_method, 'hr': 'Heart Rate (bpm)'}
                )
                fig_hr.update_traces(mode='lines+markers', marker=dict(size=4))
                fig_hr.update_layout(title="Heart Rate Profile", margin=dict(t=40, b=0, l=0, r=0))
                st.plotly_chart(fig_hr, width='stretch')
            
            col1, col2 = st.columns(2)
            with col1:
                fig_metric = px.line(
                    df, x=target_col, y='metric_value', color='Segment',
                    labels={target_col: split_method, 'metric_value': metric_name}
                )
                fig_metric.update_layout(title=f"{metric_name.split(' ')[0]} Profile", margin=dict(t=40, b=0, l=0, r=0))
                if activity_type == "Running":
                    fig_metric.update_yaxes(autorange="reversed") 
                st.plotly_chart(fig_metric, width='stretch')
                
            with col2:
                if has_watts: 
                    fig_watts = px.line(
                        df, x=target_col, y='watts', color='Segment',
                        labels={target_col: split_method, 'watts': 'Estimated Power (W)'}
                    )
                    fig_watts.update_layout(title="Power Profile", margin=dict(t=40, b=0, l=0, r=0))
                    st.plotly_chart(fig_watts, width='stretch')
                elif has_cad: 
                    fig_cad = px.line(
                        df, x=target_col, y='cad', color='Segment',
                        labels={target_col: split_method, 'cad': 'Cadence'}
                    )
                    fig_cad.update_layout(title="Cadence Profile", margin=dict(t=40, b=0, l=0, r=0))
                    st.plotly_chart(fig_cad, width='stretch')
                else:
                    st.info("No cadence or power data available to chart.")

        except Exception as e:
            st.error(f"Data processing error. Details: {e}")