import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time

# --- Page Config ---
st.set_page_config(layout="wide", page_title="🍎 Mac NPI Ramp Sequencer")

# --- Session State Initialization ---
if "input_data" not in st.session_state:
    st.session_state.input_data = pd.DataFrame({
        "Model Name": ["MacBook Air 13 (M3)", "MacBook Pro 14 (M4)", "MacBook Air 13 (M3)", "MacBook Pro 14 (M4)"],
        "Priority": ["Standard", "Standard", "Hot (VP Demo)", "Standard"],
        "Demand Qty": [40, 25, 10, 15],
        "Material On-Hand": [50, 20, 5, 20],  # Note the shortages!
        "Cycle Time (Sec)": [45, 60, 45, 60]
    })

# --- Main Title ---
st.title("🍎 Mac NPI Ramp Sequencer")
st.markdown("Optimize mixed-model lines by balancing **Efficiency**, **Priority**, and **Material Constraints (CTB)**.")

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    if st.button("🔄 Reset to Simulation"):
        st.session_state.input_data = pd.DataFrame({
            "Model Name": ["MacBook Air 13 (M3)", "MacBook Pro 14 (M4)", "MacBook Air 13 (M3)", "MacBook Pro 14 (M4)"],
            "Priority": ["Standard", "Standard", "Hot (VP Demo)", "Standard"],
            "Demand Qty": [40, 25, 10, 15],
            "Material On-Hand": [50, 20, 5, 20],
            "Cycle Time (Sec)": [45, 60, 45, 60]
        })
        st.rerun()

    shift_duration_hours = st.number_input("Shift Duration (Hours)", min_value=1.0, max_value=24.0, value=10.0, step=0.5)
    changeover_penalty_minutes = st.slider("Changeover Penalty (Minutes)", min_value=5, max_value=60, value=15, step=1)
    
    today = datetime.now().date()
    start_time = time(8, 0)
    base_start_time = datetime.combine(today, start_time)
    
    st.markdown("---")
    st.info("**Logic:** \n1. **CTB Check:** Caps build at Material Limit.\n2. **Priority:** 'Hot' runs first.\n3. **Batching:** Groups same models.")

shift_duration_seconds = shift_duration_hours * 3600
changeover_penalty_seconds = changeover_penalty_minutes * 60
shift_end_time = base_start_time + timedelta(seconds=shift_duration_seconds)

# --- Data Input Section ---
st.subheader("📋 Clear-to-Build (CTB) Plan")

mac_models = [
    "MacBook Air 13 (M3)", "MacBook Air 15 (M3)", 
    "MacBook Pro 14 (M4)", "MacBook Pro 16 (M4)", 
    "Mac mini (M4)", "Mac Studio", "Prototype (EVT)"
]
priorities = ["Hot (VP Demo)", "Standard"]

edited_df = st.data_editor(
    st.session_state.input_data,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Model Name": st.column_config.SelectboxColumn("Model Name", width="medium", options=mac_models, required=True),
        "Priority": st.column_config.SelectboxColumn("Priority", width="small", options=priorities, required=True),
        "Demand Qty": st.column_config.NumberColumn("Demand Qty", min_value=1, step=1, required=True, help="Target build count"),
        "Material On-Hand": st.column_config.NumberColumn("Material On-Hand", min_value=0, step=1, required=True, help="Constraint: Max units we have parts for"),
        "Cycle Time (Sec)": st.column_config.NumberColumn("Cycle Time (Sec)", min_value=1, step=1, required=True)
    },
    key="editor_key"
)

st.session_state.input_data = edited_df
clean_df = edited_df.dropna(how="any")

if clean_df.empty:
    st.warning("⚠️ Please add at least one row of data.")
    st.stop()

# --- Constraint Logic: Calculate Feasible vs Shortage ---
# This logic bridges Supply Chain and Operations
clean_df["Feasible Qty"] = clean_df[["Demand Qty", "Material On-Hand"]].min(axis=1)
clean_df["Shortage"] = clean_df["Demand Qty"] - clean_df["Feasible Qty"]
clean_df["Is_Short"] = clean_df["Shortage"] > 0

# Alert for Hot Shortages (The "Managerial Insight")
hot_shortages = clean_df[(clean_df["Priority"].str.contains("Hot")) & (clean_df["Is_Short"])]
if not hot_shortages.empty:
    for index, row in hot_shortages.iterrows():
        st.error(f"🚨 CRITICAL RISK: '{row['Model Name']}' (Hot) is short by {row['Shortage']} units due to material constraint!")

# --- Scheduling Logic Functions ---

def calculate_schedule(df, optimize=False):
    tasks = []
    current_time_seconds = 0
    
    if optimize:
        # 1. Define Priority Rank (Hot = 0, Standard = 1)
        priority_map = {"Hot (VP Demo)": 0, "Standard": 1}
        df = df.copy()
        df["Priority_Rank"] = df["Priority"].map(priority_map)
        
        # 2. Define Model Rank (Order of appearance)
        order = list(dict.fromkeys(df["Model Name"]))
        df["Model_Rank"] = df["Model Name"].apply(lambda x: order.index(x))
        
        # 3. MERGE: Group by Priority + Model
        # Note: We sum 'Feasible Qty' because that's all we can physically build
        process_df = df.groupby(["Priority", "Priority_Rank", "Model Name", "Model_Rank", "Cycle Time (Sec)"], as_index=False).agg({
            "Feasible Qty": "sum",
            "Demand Qty": "sum"
        })
        
        # 4. Sort: Priority first, then Model
        process_df = process_df.sort_values(by=["Priority_Rank", "Model_Rank"]).reset_index(drop=True)
    else:
        # Scenario A: FIFO
        process_df = df.copy()

    for i, row in process_df.iterrows():
        model = row["Model Name"]
        qty = row["Feasible Qty"]  # WE ONLY BUILD WHAT WE HAVE
        cycle_time = row["Cycle Time (Sec)"]
        
        # Changeover Logic
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
                "Quantity": 0,
                "Duration_Min": changeover_penalty_minutes
            })
            current_time_seconds += changeover_penalty_seconds
        
        # Production Block
        production_time = qty * cycle_time
        production_min = production_time / 60
        
        tasks.append({
            "Label": model,
            "Model": f"{model} ({qty} units)",
            "Start_Sec": current_time_seconds,
            "Finish_Sec": current_time_seconds + production_time,
            "Type": "Production",
            "Quantity": qty,
            "Duration_Min": production_min,
            "Priority": row.get("Priority", "Standard")
        })
        current_time_seconds += production_time
    
    return tasks, current_time_seconds, process_df

# Calculate Scenarios
tasks_a, total_time_a, df_a_ordered = calculate_schedule(clean_df, optimize=False)
tasks_b, total_time_b, df_b_ordered = calculate_schedule(clean_df, optimize=True)

# --- Metrics ---
time_saved_seconds = total_time_a - total_time_b
time_saved_minutes = time_saved_seconds / 60

# Calculate Total Shortage
total_shortage = clean_df["Shortage"].sum()
total_feasible = clean_df["Feasible Qty"].sum()

# Utilization Logic
prod_time_b = sum([t["Finish_Sec"] - t["Start_Sec"] for t in tasks_b if t["Type"] == "Production"])
utilization_b = (prod_time_b / total_time_b * 100) if total_time_b > 0 else 0
utilization_a = (sum([t["Finish_Sec"] - t["Start_Sec"] for t in tasks_a if t["Type"] == "Production"]) / total_time_a * 100) if total_time_a > 0 else 0
util_boost = utilization_b - utilization_a

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("⏱️ Setup Time Saved", f"{time_saved_minutes:.1f} min", delta="Optimization")
with col2:
    st.metric("🧱 Material Shortage", f"{total_shortage} units", delta="CTB Risk", delta_color="inverse", help="Units blocked by supply chain.")
with col3:
    st.metric("📈 Feasible Utilization", f"{utilization_b:.1f}%", delta=f"+{util_boost:.1f}%")

st.markdown("---")

# --- Chart Generation ---
def create_gantt(tasks, title):
    if not tasks: return None
    df_chart = pd.DataFrame(tasks)
    df_chart["Start_dt"] = base_start_time + pd.to_timedelta(df_chart["Start_Sec"], unit='s')
    df_chart["Finish_dt"] = base_start_time + pd.to_timedelta(df_chart["Finish_Sec"], unit='s')
    
    def smart_label(row):
        if row["Type"] == "Changeover": return ""
        if row["Duration_Min"] < 15: return ""
        prefix = "🔥 " if "Hot" in str(row.get("Priority","")) else ""
        return f"{prefix}{row['Label']}"
    
    df_chart["Display_Text"] = df_chart.apply(smart_label, axis=1)
    
    color_map = {"Production": "#22c55e", "Changeover": "#ef4444"}
    
    fig = px.timeline(
        df_chart,
        x_start="Start_dt", x_end="Finish_dt", y="Type", color="Type",
        color_discrete_map=color_map, text="Display_Text",
        hover_data={"Model": True, "Quantity": True, "Priority": True}
    )
    
    fig.add_vline(x=shift_end_time.timestamp() * 1000, line_width=2, line_dash="dash", line_color="white", annotation_text="End of Shift")
    fig.update_yaxes(visible=False)
    fig.update_xaxes(tickformat="%H:%M", title_text="Time")
    fig.update_traces(textposition='inside', insidetextanchor='middle', textfont=dict(size=11, color='white'))
    fig.update_layout(
        title=title, showlegend=True, height=280,
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)", title_text=""),
        uniformtext_minsize=8, uniformtext_mode='hide'
    )
    return fig

col_chart1, col_chart2 = st.columns(2)
with col_chart1:
    st.plotly_chart(create_gantt(tasks_a, "Scenario A: Unoptimized (FIFO)"), use_container_width=True)
with col_chart2:
    st.plotly_chart(create_gantt(tasks_b, "Scenario B: Optimized (Priority + Material Aware)"), use_container_width=True)

# --- Actionable Shortage Table ---
st.markdown("### ⚠️ Critical Material Shortages")
shortage_df = clean_df[clean_df["Shortage"] > 0].copy()
if not shortage_df.empty:
    st.dataframe(
        shortage_df[["Priority", "Model Name", "Demand Qty", "Material On-Hand", "Shortage"]],
        use_container_width=True,
        column_config={
            "Shortage": st.column_config.NumberColumn("Missing Parts", format="%d ⚠️"),
        },
        hide_index=True
    )
else:
    st.success("✅ All builds are Clear-to-Build (CTB)!")

st.markdown(
    """
    <div style="text-align: center; color: grey; font-size: 12px; margin-top: 50px;">
        Prototype built for NPI Capacity Planning by 
        <a href="https://www.linkedin.com/in/vashistrahul29/" target="_blank" style="color: grey; text-decoration: none;"><b>Rahul Vashisht</b></a> 
        | 2026
    </div>
    """,
    unsafe_allow_html=True
)
