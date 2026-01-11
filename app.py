import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

# --- Page Config ---
st.set_page_config(layout="wide", page_title="🍎 NPI Ramp Sequencer")

# --- Session State Initialization (Fixes Data Persistence) ---
# This ensures data doesn't disappear when you adjust sliders
if "input_data" not in st.session_state:
    st.session_state.input_data = pd.DataFrame({
        "Model Name": ["MacBook Air 13 (M3)", "MacBook Pro 14 (M4)", "MacBook Air 13 (M3)", "MacBook Pro 14 (M4)"],
        "Quantity": [40, 25, 30, 15],
        "Cycle Time (Sec)": [45, 60, 45, 60]
    })

# --- Main Title ---
st.title("🍎 Mac NPI Ramp Sequencer")
st.markdown("Optimize mixed-model assembly lines to minimize changeover loss and maximize UPH.")

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Reset Button
    if st.button("🔄 Reset to Default Plan"):
        st.session_state.input_data = pd.DataFrame({
            "Model Name": ["MacBook Air 13 (M3)", "MacBook Pro 14 (M4)", "MacBook Air 13 (M3)", "MacBook Pro 14 (M4)"],
            "Quantity": [40, 25, 30, 15],
            "Cycle Time (Sec)": [45, 60, 45, 60]
        })
        st.rerun()

    shift_duration_hours = st.number_input("Shift Duration (Hours)", min_value=1.0, max_value=24.0, value=10.0, step=0.5)
    changeover_penalty_minutes = st.slider("Changeover Penalty (Minutes)", min_value=5, max_value=60, value=15, step=1)
    
    # Define a base start time (Today at 08:00 AM)
    today = datetime.now().date()
    start_time = time(8, 0)
    base_start_time = datetime.combine(today, start_time)
    
    st.markdown("---")
    st.info("**Logic:** Penalty applies whenever the Model Type changes from the previous batch.")

shift_duration_seconds = shift_duration_hours * 3600
changeover_penalty_seconds = changeover_penalty_minutes * 60
shift_end_time = base_start_time + timedelta(seconds=shift_duration_seconds)

# --- Data Input Section ---
st.subheader("📋 Day Plan Input")

# Define Mac Models for Dropdown (Faster Entry)
mac_models = [
    "MacBook Air 13 (M3)", "MacBook Air 15 (M3)", 
    "MacBook Pro 14 (M4)", "MacBook Pro 16 (M4)", 
    "Mac mini (M4)", "Mac Studio", "Mac Pro", "Prototype (EVT)"
]

# Editable Data Grid
edited_df = st.data_editor(
    st.session_state.input_data,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Model Name": st.column_config.SelectboxColumn(
            "Model Name",
            help="Select the Mac SKU",
            width="medium",
            options=mac_models,
            required=True
        ),
        "Quantity": st.column_config.NumberColumn(
            "Quantity",
            help="Units to build",
            min_value=1,
            step=1,
            required=True
        ),
        "Cycle Time (Sec)": st.column_config.NumberColumn(
            "Cycle Time (Sec)",
            help="Standard time per unit",
            min_value=1,
            step=1,
            required=True
        )
    },
    key="editor_key" # Key needed for session state interaction
)

# Sync editor changes back to session state
st.session_state.input_data = edited_df

# Validation: Drop empty rows to prevent crashes
clean_df = edited_df.dropna(how="any")

# Stop if data is invalid
if clean_df.empty:
    st.warning("⚠️ Please add at least one row of data to generate the schedule.")
    st.stop()

# --- Logic Functions ---

def calculate_schedule(df, optimize=False):
    tasks = []
    current_time_seconds = 0
    
    # If optimizing, sort by Model Name first to group batches
    if optimize:
        # Custom sort: Maintain first appearance order but group duplicates
        order = list(dict.fromkeys(df["Model Name"]))
        df = df.copy()
        df["Model_Rank"] = df["Model Name"].apply(lambda x: order.index(x))
        process_df = df.sort_values(by=["Model_Rank"]).reset_index(drop=True)
    else:
        process_df = df.copy()

    for i, row in process_df.iterrows():
        model = row["Model Name"]
        qty = row["Quantity"]
        cycle_time = row["Cycle Time (Sec)"]
        
        # Check if changeover needed
        is_changeover = False
        if i > 0:
            prev_model = process_df.iloc[i-1]["Model Name"]
            if prev_model != model:
                is_changeover = True
        
        # Add Changeover Block
        if is_changeover:
            tasks.append({
                "Label": "Setup",
                "Model": f"Changeover to {model}",
                "Start_Sec": current_time_seconds,
                "Finish_Sec": current_time_seconds + changeover_penalty_seconds,
                "Type": "Changeover",
                "Quantity": 0,
                "Duration_Min": changeover_penalty_minutes
            })
            current_time_seconds += changeover_penalty_seconds
        
        # Add Production Block
        production_time = qty * cycle_time
        production_min = production_time / 60
        tasks.append({
            "Label": model, # Short label for the bar
            "Model": f"{model} ({qty} units)",
            "Start_Sec": current_time_seconds,
            "Finish_Sec": current_time_seconds + production_time,
            "Type": "Production",
            "Quantity": qty,
            "Duration_Min": production_min
        })
        current_time_seconds += production_time
    
    return tasks, current_time_seconds, process_df

# Calculate Scenarios
tasks_a, total_time_a, df_a_ordered = calculate_schedule(clean_df, optimize=False)
tasks_b, total_time_b, df_b_ordered = calculate_schedule(clean_df, optimize=True)

# --- Metrics Calculation ---

time_saved_seconds = total_time_a - total_time_b
time_saved_minutes = time_saved_seconds / 60

# Calculate Production Time only (excluding changeovers)
prod_time_a = sum([t["Finish_Sec"] - t["Start_Sec"] for t in tasks_a if t["Type"] == "Production"])
prod_time_b = sum([t["Finish_Sec"] - t["Start_Sec"] for t in tasks_b if t["Type"] == "Production"])

utilization_a = (prod_time_a / total_time_a * 100) if total_time_a > 0 else 0
utilization_b = (prod_time_b / total_time_b * 100) if total_time_b > 0 else 0
utilization_boost = utilization_b - utilization_a

avg_cycle_time = clean_df["Cycle Time (Sec)"].mean()
recovered_units = int(time_saved_seconds / avg_cycle_time) if avg_cycle_time > 0 else 0

# --- Display Metrics ---

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("⏱️ Time Saved", f"{time_saved_minutes:.1f} min", delta="Reduction in waste", help="Total reduction in shift length due to optimized sequencing.")
with col2:
    st.metric("📈 Utilization Boost", f"{utilization_b:.1f}%", delta=f"+{utilization_boost:.1f}%", help="New Utilization % vs Old.")
with col3:
    st.metric("🎯 Recovered Units", f"{recovered_units} units", delta="Free Capacity", help=f"Extra units you could build in the saved time (Avg Cycle: {avg_cycle_time:.0f}s).")

st.markdown("---")

# --- Chart Generation ---

def create_gantt(tasks, title):
    if not tasks:
        return None
        
    df_chart = pd.DataFrame(tasks)
    
    # Convert seconds to Real Datetimes
    df_chart["Start_dt"] = base_start_time + pd.to_timedelta(df_chart["Start_Sec"], unit='s')
    df_chart["Finish_dt"] = base_start_time + pd.to_timedelta(df_chart["Finish_Sec"], unit='s')
    
    # --- Smart Labelling Logic ---
    # Only show text if the block is wide enough (> 15 mins) to prevent clutter
    def smart_label(row):
        if row["Duration_Min"] < 15: 
            return "" 
        return row["Label"]
    
    df_chart["Display_Text"] = df_chart.apply(smart_label, axis=1)
    
    # Color Map
    color_map = {"Production": "#22c55e", "Changeover": "#ef4444"}
    
    fig = px.timeline(
        df_chart,
        x_start="Start_dt",
        x_end="Finish_dt",
        y="Type", 
        color="Type",
        color_discrete_map=color_map,
        text="Display_Text", 
        hover_data={"Model": True, "Quantity": True, "Label": False, "Type": False, "Display_Text": False, "Duration_Min": True}
    )
    
    # Add "End of Shift" Line
    fig.add_vline(x=shift_end_time.timestamp() * 1000, line_width=2, line_dash="dash", line_color="white", annotation_text="End of Shift")

    fig.update_yaxes(visible=False) 
    fig.update_xaxes(
        tickformat="%H:%M", 
        title_text="Time (Shift Start: 08:00)"
    )
    
    fig.update_traces(textposition='inside', insidetextanchor='middle')
    
    fig.update_layout(
        title=title,
        showlegend=True,
        height=280,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", y=1.1),
        uniformtext_minsize=10, 
        uniformtext_mode='hide'
    )
    return fig

# Display Charts
col_chart1, col_chart2 = st.columns(2)
with col_chart1:
    st.plotly_chart(create_gantt(tasks_a, "Scenario A: Current Sequence (Fragmented)"), use_container_width=True)
with col_chart2:
    st.plotly_chart(create_gantt(tasks_b, "Scenario B: Optimized Sequence (Consolidated)"), use_container_width=True)

# --- Optimized Work Order Table (New Feature) ---
st.markdown("### 📝 Optimized Work Order")
st.markdown("Actionable sequence for the line manager:")

# Create a clean summary table from the Optimized data
work_order = df_b_ordered.groupby("Model Name", sort=False).agg({
    "Quantity": "sum",
    "Cycle Time (Sec)": "first"
}).reset_index()

# Calculate duration for each batch
work_order["Batch Duration (Min)"] = (work_order["Quantity"] * work_order["Cycle Time (Sec)"]) / 60
work_order["Batch Duration (Min)"] = work_order["Batch Duration (Min)"].round(1)

# Display as a clean table
st.dataframe(
    work_order,
    use_container_width=True,
    column_config={
        "Model Name": "Model / SKU",
        "Quantity": "Total Batch Size",
        "Cycle Time (Sec)": "Cycle Time (s)",
        "Batch Duration (Min)": st.column_config.NumberColumn("Est. Duration (min)", format="%.1f min")
    },
    hide_index=True
)

st.caption(f"Prototype built for NPI Capacity Planning | {datetime.now().year}")
