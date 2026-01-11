import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="🍎 NPI Ramp Sequencer")

st.title("🍎 Mac NPI Ramp Sequencer")

# Sidebar Configuration
with st.sidebar:
    shift_duration_hours = st.number_input("Shift Duration (Hours)", min_value=1.0, max_value=24.0, value=10.0, step=0.5)
    changeover_penalty_minutes = st.slider("Changeover Penalty (Minutes)", min_value=5, max_value=60, value=15, step=1)
    st.markdown("**Note:** Penalty applies whenever the Model Type changes.")

shift_duration_seconds = shift_duration_hours * 3600
changeover_penalty_seconds = changeover_penalty_minutes * 60

# Default Data - The "Broken Batch" Story
default_data = pd.DataFrame({
    "Model Name": ["MacBook Air M3", "MacBook Pro M4", "MacBook Air M3", "MacBook Pro M4"],
    "Quantity": [40, 25, 30, 15],
    "Cycle Time (Sec)": [45, 60, 45, 60]
})

st.subheader("📋 Day Plan Input")
st.markdown("Enter your production plan for the day:")

edited_df = st.data_editor(
    default_data,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Model Name": st.column_config.TextColumn("Model Name", required=True),
        "Quantity": st.column_config.NumberColumn("Quantity", min_value=1, required=True),
        "Cycle Time (Sec)": st.column_config.NumberColumn("Cycle Time (Sec)", min_value=1, required=True)
    }
)

if edited_df.empty or edited_df["Model Name"].isnull().any() or edited_df["Quantity"].isnull().any() or edited_df["Cycle Time (Sec)"].isnull().any():
    st.warning("⚠️ Please ensure all rows have valid data.")
    st.stop()

# Scenario A: Current Sequence (FIFO)
def calculate_scenario_a(df):
    tasks = []
    current_time = 0
    
    for i, row in df.iterrows():
        model = row["Model Name"]
        qty = row["Quantity"]
        cycle_time = row["Cycle Time (Sec)"]
        
        # Check if changeover needed
        if i > 0 and df.iloc[i-1]["Model Name"] != model:
            # Add changeover
            tasks.append({
                "Model": f"Changeover ({model})",
                "Start": current_time,
                "Finish": current_time + changeover_penalty_seconds,
                "Type": "Changeover",
                "Quantity": 0
            })
            current_time += changeover_penalty_seconds
        
        # Add production
        production_time = qty * cycle_time
        tasks.append({
            "Model": model,
            "Start": current_time,
            "Finish": current_time + production_time,
            "Type": "Production",
            "Quantity": qty
        })
        current_time += production_time
    
    return tasks, current_time

# Scenario B: Optimized (Consolidated)
def calculate_scenario_b(df):
    # Group by model
    grouped = df.groupby("Model Name", sort=False).agg({
        "Quantity": "sum",
        "Cycle Time (Sec)": "first"
    }).reset_index()
    
    tasks = []
    current_time = 0
    
    for i, row in grouped.iterrows():
        model = row["Model Name"]
        qty = row["Quantity"]
        cycle_time = row["Cycle Time (Sec)"]
        
        # Changeover needed for each model (except first)
        if i > 0:
            tasks.append({
                "Model": f"Changeover ({model})",
                "Start": current_time,
                "Finish": current_time + changeover_penalty_seconds,
                "Type": "Changeover",
                "Quantity": 0
            })
            current_time += changeover_penalty_seconds
        
        # Add production
        production_time = qty * cycle_time
        tasks.append({
            "Model": model,
            "Start": current_time,
            "Finish": current_time + production_time,
            "Type": "Production",
            "Quantity": qty
        })
        current_time += production_time
    
    return tasks, current_time

tasks_a, total_time_a = calculate_scenario_a(edited_df)
tasks_b, total_time_b = calculate_scenario_b(edited_df)

df_a = pd.DataFrame(tasks_a)
df_b = pd.DataFrame(tasks_b)

# Calculate Metrics
time_saved_seconds = total_time_a - total_time_b
time_saved_minutes = time_saved_seconds / 60

production_time_a = sum([t["Finish"] - t["Start"] for t in tasks_a if t["Type"] == "Production"])
production_time_b = sum([t["Finish"] - t["Start"] for t in tasks_b if t["Type"] == "Production"])

utilization_a = (production_time_a / total_time_a * 100) if total_time_a > 0 else 0
utilization_b = (production_time_b / total_time_b * 100) if total_time_b > 0 else 0
utilization_boost = utilization_b - utilization_a

avg_cycle_time = edited_df["Cycle Time (Sec)"].mean()
recovered_units = int(time_saved_seconds / avg_cycle_time) if avg_cycle_time > 0 else 0

# Display Metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("⏱️ Time Saved", f"{time_saved_minutes:.1f} min")
with col2:
    st.metric("📈 Utilization Boost", f"+{utilization_boost:.1f}%")
with col3:
    st.metric("🎯 Recovered Units", f"{recovered_units} units")

st.markdown("---")

# Prepare data for Gantt charts
df_a["Start_dt"] = pd.to_datetime(df_a["Start"], unit='s')
df_a["Finish_dt"] = pd.to_datetime(df_a["Finish"], unit='s')
df_a["Scenario"] = "A: Current Sequence"

df_b["Start_dt"] = pd.to_datetime(df_b["Start"], unit='s')
df_b["Finish_dt"] = pd.to_datetime(df_b["Finish"], unit='s')
df_b["Scenario"] = "B: Optimized Sequence"

# Color mapping
color_map = {"Production": "#22c55e", "Changeover": "#ef4444"}

# Create Gantt Charts
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Scenario A: Current Sequence (Fragmented)")
    fig_a = px.timeline(
        df_a,
        x_start="Start_dt",
        x_end="Finish_dt",
        y="Type",
        color="Type",
        color_discrete_map=color_map,
        hover_data={"Model": True, "Quantity": True, "Start_dt": False, "Finish_dt": False, "Type": False}
    )
    fig_a.update_yaxes(autorange="reversed")
    fig_a.update_layout(
        showlegend=True,
        height=400,
        xaxis_title="Time",
        yaxis_title="",
        hovermode="closest"
    )
    st.plotly_chart(fig_a, use_container_width=True)

with col_chart2:
    st.subheader("Scenario B: Optimized Sequence (Consolidated)")
    fig_b = px.timeline(
        df_b,
        x_start="Start_dt",
        x_end="Finish_dt",
        y="Type",
        color="Type",
        color_discrete_map=color_map,
        hover_data={"Model": True, "Quantity": True, "Start_dt": False, "Finish_dt": False, "Type": False}
    )
    fig_b.update_yaxes(autorange="reversed")
    fig_b.update_layout(
        showlegend=True,
        height=400,
        xaxis_title="Time",
        yaxis_title="",
        hovermode="closest"
    )
    st.plotly_chart(fig_b, use_container_width=True)

st.markdown("---")
st.caption("Prototype built for NPI Capacity Planning")
