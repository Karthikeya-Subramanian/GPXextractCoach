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
    if pd.isna(decimal_minutes) or decimal_minutes == float('inf'):
        return "0:00"
    mins = int(decimal_minutes)
    secs = int(round((decimal_minutes - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
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
        pdf.set_font('Arial', 'B', 8) # slightly smaller font to fit new columns
        
        # Calculate column width to fit page
        epw = pdf.w - 2 * pdf.l_margin
        col_width = epw / len(df.columns)
        row_height = 8
        
        # Table Header
        for col in df.columns:
            pdf.cell(col_width, row_height, str(col), border=1, align='C')
        pdf.ln()
        
        # Table Rows
        pdf.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            for item in row:
                pdf.cell(col_width, row_height, str(item), border=1, align='C')
            pdf.ln()
        pdf.ln(5)

    # Add the main summary table
    add_table_to_pdf(summary_df, "Overall Workout Summary")
    
    # Add each of the sub-segment tables
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
                    'time': point.time,
                    'lat': point.latitude,
                    'lon': point.longitude,
                    'elevation': point.elevation if point.elevation is not None else 0.0,
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
    
    df['ele_diff'] = df['elevation'].diff().fillna(0)
    df['ele_gain'] = df['ele_diff'].clip(lower=0)
    
    if 'cad' not in df.columns:
        df['cad'] = np.nan
    if 'hr' not in df.columns:
        df['hr'] = np.nan
        
    df['cum_distance_km'] = df['distance_m'].cumsum() / 1000
    df['cum_time_min'] = df['time_diff_s'].cumsum() / 60
    
    df['speed_m_s'] = df['distance_m'].rolling(5, min_periods=1).sum() / df['time_diff_s'].rolling(5, min_periods=1).sum()
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.bfill(inplace=True)
    
    return df


# --- Main App UI ---
st.title("GPX Workout Analyzer")
st.markdown("Upload your structured workout data to visualize splits, pace, heart rate zones, and power/elevation metrics.")

uploaded_file = st.file_uploader("Select GPX File", type=["gpx"])

if uploaded_file is not None:
    df = parse_gpx(uploaded_file.getvalue())
    
    st.sidebar.header("Configuration")
    activity_type = st.sidebar.radio("Activity Profile", ["Running", "Cycling"])
    
    if activity_type == "Running":
        df['metric_value'] = 16.666666666667 / df['speed_m_s'] 
        df.loc[df['metric_value'] > 20, 'metric_value'] = 20 
        metric_name = "Pace (min/km)"
        
        if not df['cad'].isna().all():
            df['cad'] = df['cad'] * 2 
            df['stride_length_m'] = np.where(df['cad'] > 0, (df['speed_m_s'] * 60) / df['cad'], 0)
            
    else: # Cycling
        df['metric_value'] = df['speed_m_s'] * 3.6
        metric_name = "Speed (km/h)"
        
        st.sidebar.subheader("Power Estimation Metrics")
        mass = st.sidebar.number_input("Rider + Bike Weight (kg)", value=80.0)
        Crr = st.sidebar.number_input("Rolling Resistance (Crr)", value=0.008, format="%.3f", help="0.005=Smooth, 0.007=Rough, 0.009=Broken")
        CdA = st.sidebar.number_input("Aero Drag (CdA)", value=0.38, format="%.2f", help="0.32=Road Drops, 0.45=Upright")
        rho = st.sidebar.number_input("Air Density (kg/m^3)", value=1.11, format="%.2f", help="1.22=Sea Level, 1.08=Bangalore")
        
        g = 9.81
        grade_decimal = df['ele_diff'] / df['distance_m']
        grade_decimal = grade_decimal.replace([np.inf, -np.inf], 0).fillna(0)
        v = df['speed_m_s']
        
        F_gravity = mass * g * grade_decimal
        F_rolling = mass * g * Crr
        F_drag = 0.5 * rho * CdA * (v ** 2)
        raw_power = (F_gravity + F_rolling + F_drag) * v
        df['watts'] = raw_power.clip(lower=0)

    st.sidebar.subheader("Interval Segmentation")
    split_method = st.sidebar.selectbox("Segment Metric", ["Distance (km)", "Time (minutes)"])
    
    placeholder = "3, 6, 3" if split_method == "Distance (km)" else "3, 5, 1, 5, 1, 3"
    splits_input = st.sidebar.text_input("Interval Values (comma separated)", placeholder)
    
    if splits_input:
        try:
            split_lengths = [float(x.strip()) for x in splits_input.split(',') if x.strip()]
            bins = [0] + list(np.cumsum(split_lengths))
            bins.append(float('inf')) 
            
            labels = [f"Split {i+1} ({val})" for i, val in enumerate(split_lengths)] + ["Remaining"]
            target_col = 'cum_distance_km' if split_method == "Distance (km)" else 'cum_time_min'
            
            df['Segment'] = pd.cut(df[target_col], bins=bins, labels=labels, right=True)
            df = df[df['Segment'].notna()]
            
            has_hr = not df['hr'].isna().all()
            has_cad = not df['cad'].isna().all()
            has_stride = 'stride_length_m' in df.columns
            has_watts = 'watts' in df.columns
            
            # --- Aggregation Dictionary ---
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
                summary[f'Avg {metric_name}'] = summary['Time_min'] / summary['Distance (km)']
            else:
                summary[f'Avg {metric_name}'] = summary['Distance (km)'] / (summary['Time_min'] / 60)
                
            summary['Gradient (%)'] = np.where(summary['Distance (km)'] > 0, 
                                              (summary['ele_diff'] / (summary['Distance (km)'] * 1000)) * 100, 0)
            summary['Elev Gain (m)'] = summary['ele_gain']
            
            # Formatting Summary Table
            display_summary = summary.copy()
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
                
            st.dataframe(display_summary[display_cols])
            
            # --- Sub-Segment Detailed Splits ---
            st.markdown("### Lap Details")
            pdf_detailed_dfs = {}
            
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
                    sub_summary.rename(columns={'distance_m': 'Distance (km)', 'time_diff_s': 'Time_min'}, inplace=True)
                    
                    if activity_type == "Running":
                        sub_summary[f'Avg {metric_name}'] = sub_summary['Time_min'] / sub_summary['Distance (km)']
                    else:
                        sub_summary[f'Avg {metric_name}'] = sub_summary['Distance (km)'] / (sub_summary['Time_min'] / 60)
                    
                    sub_summary['Gradient (%)'] = np.where(sub_summary['Distance (km)'] > 0, 
                                                          (sub_summary['ele_diff'] / (sub_summary['Distance (km)'] * 1000)) * 100, 0)
                    sub_summary['Elev Gain (m)'] = sub_summary['ele_gain']

                    # Formatting Sub-Segment Table
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
                    st.dataframe(final_sub_df)
                    
                    # Save the dataframe for the PDF exporter
                    pdf_detailed_dfs[segment_name] = final_sub_df

            # --- PDF Download Button ---
            st.markdown("---")
            pdf_bytes = generate_pdf_report(activity_type, display_summary[display_cols], pdf_detailed_dfs)
            
            st.download_button(
                label="📄 Download Report as PDF",
                data=pdf_bytes,
                file_name="workout_report.pdf",
                mime="application/pdf"
            )
            st.markdown("---")

            # --- Visualizations ---
            st.markdown("### Telemetry")
            
            if has_hr:
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
                if has_watts: # Cycling Watts graph
                    fig_watts = px.line(
                        df, x=target_col, y='watts', color='Segment',
                        labels={target_col: split_method, 'watts': 'Estimated Power (W)'}
                    )
                    fig_watts.update_layout(title="Power Profile", margin=dict(t=40, b=0, l=0, r=0))
                    st.plotly_chart(fig_watts, width='stretch')
                elif has_cad: # Running Cadence graph
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