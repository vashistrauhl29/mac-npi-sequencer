import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

st.set_page_config(layout="wide", page_title=" NPI Ramp Sequencer")

st.title(" Mac NPI Ramp Sequencer")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    shift_duration_hours = st.number_input("Shift Duration (Hours)", min_value=1.0, max_value=24.0, value=10.0, step=0.5)
    changeover_penalty_minutes = st.slider("Changeover Penalty (Minutes)", min_value=5, max_value=60, value=15, step=1)
    
    # Define a base start time (Today at 08:00 AM)
    today = datetime.now().date()
    start_time = time(8, 0)
    base_start_time = datetime.combine(today, start_time)
    
    st.markdown("---")
    st.markdown("**Logic:** Penalty applies whenever the Model Type changes.")

shift_duration_seconds = shift_duration_hours * 3600
changeover_penalty_seconds = changeover_penalty_minutes * 60
shift_end_time = base_start_time + timedelta(seconds=shift_duration_seconds)

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

# --- Logic Functions ---

def calculate_schedule(df, optimize=False):
    tasks = []
    current_time_seconds = 0
    
    # If optimizing, sort by Model Name first
    if optimize:
        # Group by Model to consolidate batches
        # We use a custom sort to keep the first appearance order but group duplicates
        order = list(dict.fromkeys(df["Model Name"]))
        df["Model_Rank"] = df["Model Name"].apply(lambda x: order.index(x))
        process_df = df.sort_values(by=["Model_Rank"]).reset_index(drop=True)
    else:
        process_df = df.copy()

    for i, row in process_df.iterrows():
        model = row["Model Name"]
        qty = row["Quantity"]
        cycle_time = row["Cycle Time (Sec)"]
        
        # Check if changeover needed
        # (For optimized, we check if model changes from previous row in the SORTED list)
        is_changeover = False
        if i > 0:
            prev_model = process_df.iloc[i-1]["Model Name"]
            if prev_model != model:
                is_changeover = True
        
        if is_changeover:
            tasks.append({
                "Label": "Setup",
                "Model": f"Changeover to {model}",
                "Start_Sec": current_time_seconds,
                "Finish_Sec": current_time_seconds + changeover_penalty_seconds,
                "Type": "Changeover",
                "Quantity": 0
            })
            current_time_seconds += changeover_penalty_seconds
        
        # Add production
        production_time = qty * cycle_time
        tasks.append({
            "Label": model, # Short label for the bar
            "Model": f"{model} ({qty} units)",
            "Start_Sec": current_time_seconds,
            "Finish_Sec": current_time_seconds + production_time,
            "Type": "Production",
            "Quantity": qty
        })
        current_time_seconds += production_time
    
    return tasks, current_time_seconds

# Calculate Scenarios
tasks_a, total_time_a = calculate_schedule(edited_df, optimize=False)
tasks_b, total_time_b = calculate_schedule(edited_df, optimize=True)

# --- Metrics Calculation ---

time_saved_seconds = total_time_a - total_time_b
time_saved_minutes = time_saved_seconds / 60

# Calculate Production Time only (excluding changeovers)
prod_time_a = sum([t["Finish_Sec"] - t["Start_Sec"] for t in tasks_a if t["Type"] == "Production"])
prod_time_b = sum([t["Finish_Sec"] - t["Start_Sec"] for t in tasks_b if t["Type"] == "Production"])

utilization_a = (prod_time_a / total_time_a * 100) if total_time_a > 0 else 0
utilization_b = (prod_time_b / total_time_b * 100) if total_time_b > 0 else 0
utilization_boost = utilization_b - utilization_a

avg_cycle_time = edited_df["Cycle Time (Sec)"].mean()
recovered_units = int(time_saved_seconds / avg_cycle_time) if avg_cycle_time > 0 else 0

# --- Display Metrics ---

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("⏱️ Time Saved", f"{time_saved_minutes:.1f} min", help="Total reduction in shift length due to optimized sequencing.")
with col2:
    st.metric("📈 Utilization Boost", f"+{utilization_boost:.1f}%", help="Increase in % of shift time spent actually building units.")
with col3:
    st.metric("🎯 Recovered Units", f"{recovered_units} units", help=f"Extra units you could build in the saved time (Avg Cycle: {avg_cycle_time:.0f}s).")

st.markdown("---")

# --- Chart Generation ---

def create_gantt(tasks, title):
    if not tasks:
        return None
        
    df_chart = pd.DataFrame(tasks)
    
    # Convert seconds to Real Datetimes
    df_chart["Start_dt"] = base_start_time + pd.to_timedelta(df_chart["Start_Sec"], unit='s')
    df_chart["Finish_dt"] = base_start_time + pd.to_timedelta(df_chart["Finish_Sec"], unit='s')
    
    # Color Map
    color_map = {"Production": "#22c55e", "Changeover": "#ef4444"}
    
    fig = px.timeline(
        df_chart,
        x_start="Start_dt",
        x_end="Finish_dt",
        y="Type", # Use Type to categorize rows
        color="Type",
        color_discrete_map=color_map,
        text="Label", # Show Model Name inside the bar
        hover_data={"Model": True, "Quantity": True, "Label": False, "Type": False}
    )
    
    # Add "End of Shift" Line
    fig.add_vline(x=shift_end_time.timestamp() * 1000, line_width=2, line_dash="dash", line_color="white", annotation_text="End of Shift")

    fig.update_yaxes(visible=False) # Hide Y axis labels (cleaner look)
    fig.update_xaxes(
        tickformat="%H:%M", # Show 08:00, 09:00, etc.
        title_text="Time (Shift Start: 08:00)"
    )
    fig.update_layout(
        title=title,
        showlegend=True,
        height=250,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", y=1.1)
    )
    return fig

# Display Charts
st.plotly_chart(create_gantt(tasks_a, "Scenario A: Current Sequence (Fragmented)"), use_container_width=True)
st.plotly_chart(create_gantt(tasks_b, "Scenario B: Optimized Sequence (Consolidated)"), use_container_width=True)

st.markdown("---")
st.caption("Prototype built for NPI Capacity Planning | Rahul Vashisht")
