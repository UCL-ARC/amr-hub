# ruff: noqa: D100, D103, D400, D401, D415, E501, ANN201, T201, B905, ANN001
"""
UCLARC: Nicolin Govender
Updated for GPU-Accelerated AMR-Hub Test Output
"""

import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from enum import IntEnum

#=====================================================================
# Enums and Config
#=====================================================================
class InfectionStatus(IntEnum):
    SUSCEPTIBLE = 0
    EXPOSED     = 1
    INFECTED    = 2
    RECOVERED   = 3

#=====================================================================
# A] Load Telemetry and Events
#=====================================================================
print("Loading Simulation Results")

telemetry_path = "../python-code/simulation_outputs/gpu_sim_telemetry.csv"
events_path    = "../python-code/simulation_outputs/gpu_sim_events.csv"
cad_path       = "floorplan_simple_a.npz"

# Load Telemetry
df = pd.read_csv(telemetry_path)
if 'status' in df.columns:
    df.rename(columns={'status': 'infection_status'}, inplace=True)

#---------------------------------------------------------------------------------
# 0. Separate Agent (A) and Patient (P) IDs
df['agent_id'] = df['agent_id'].astype(str)

# Pre-format all standalone IDs to start with 'A'
df['agent_id'] = df['agent_id'].apply(lambda x: x if x.startswith('A') else f"A{x}")

dup_agents = df[df.duplicated(['time', 'agent_id'])]['agent_id'].unique()

if len(dup_agents) > 0:
    print("Resolving duplicate paths")
    for aid in dup_agents:
        mask = df['agent_id'] == aid
        subset = df[mask].sort_values('time')

        last_pos = {}
        resolved_ids = []

        # 1. Map physical paths via Nearest-Neighbor
        for t, group in subset.groupby('time'):
            if not last_pos:
                for i, row in enumerate(group.itertuples()):
                    uid = f"Trk{i}"
                    last_pos[uid] = (row.pos_x, row.pos_y)
                    resolved_ids.append(uid)
            else:
                available_uids = list(last_pos.keys())
                for row in group.itertuples():
                    best_uid = available_uids[0]
                    min_d = float('inf')
                    for uid in available_uids:
                        px, py = last_pos[uid]
                        d = (row.pos_x - px)**2 + (row.pos_y - py)**2
                        if d < min_d:
                            min_d = d
                            best_uid = uid
                    resolved_ids.append(best_uid)
                    last_pos[best_uid] = (row.pos_x, row.pos_y)
                    available_uids.remove(best_uid)

        subset['temp_id'] = resolved_ids

        # 2. Assign A (moving track) and P (stationary track)
        track_variances = subset.groupby('temp_id')[['pos_x', 'pos_y']].var().sum(axis=1)
        hcw_trk = track_variances.idxmax()

        num = aid.replace('A', '') # Strip 'A' to get raw number

        def map_id(trk):
            return f"A{num}" if trk == hcw_trk else f"P{num}"

        subset['final_id'] = subset['temp_id'].apply(map_id)
        df.loc[subset.index, 'agent_id'] = subset['final_id']
#---------------------------------------------------------------------------------

#---------------------------------------------------------------------------------
# 1. Add to html
times = sorted(df['time'].unique())
max_time = times[-1] if times else 0

# Load Events and Build Dropdown Options
event_options = []
try:
    df_events = pd.read_csv(events_path)
    df_events.rename(columns={
        'source_id': 'infector',
        'target_id': 'infectee',
        'location_x': 'pos_x',
        'location_y': 'pos_y'
    }, inplace=True)

    unique_events = sorted(df_events['time'].unique())
    event_options = [{'label': f"Transmission at t={t}s", 'value': t} for t in unique_events]
    if not event_options:
        event_options = [{'label': "No Transmissions Occurred", 'value': 0, 'disabled': True}]

except FileNotFoundError:
    print(f"Events file not found at {events_path}. Proceeding without event markers.")
    df_events = pd.DataFrame(columns=['time', 'infector', 'infectee', 'pos_x', 'pos_y'])
    event_options = [{'label': "❌ Event File Missing", 'value': 0, 'disabled': True}]
#---------------------------------------------------------------------------------

#=====================================================================


#=====================================================================
# B] Load Semantic CAD Geometry
#=====================================================================
print("Loading CAD Asset")
geom = np.load(cad_path, allow_pickle=True)

wall_v = geom['wall_vertices']
wall_x, wall_y = [], []

for i in range(0, len(wall_v), 4):
    p1 = wall_v[i]
    p2 = wall_v[i+1]
    wall_x.extend([float(p1[0]), float(p2[0]), None])
    wall_y.extend([float(p1[1]), float(p2[1]), None])

if 'room_coords' in geom and 'room_names' in geom:
    room_coords = geom['room_coords']
    room_names = geom['room_names']
    room_x = [float(c[0]) for c in room_coords]
    room_y = [float(c[1]) for c in room_coords]
else:
    room_x, room_y, room_names = [], [], []

beds = geom['beds'] if 'beds' in geom else []

door_coords = {}
if 'doors' in geom:
    for i, door_pts in enumerate(geom['doors']):
        door_id = i + 1
        door_coords[door_id] = {
            'x': [float(door_pts[0][0]), float(door_pts[1][0])],
            'y': [float(door_pts[0][1]), float(door_pts[1][1])]
        }
print("Data and Geometry Loaded successfully!")
#=====================================================================


#=====================================================================
# C] Build Dash Layout
#=====================================================================
app = dash.Dash(__name__)
app.title = "GPU Sim Test Viewer"

app.layout = html.Div(style={'backgroundColor': '#F8F9FA', 'color': '#212529', 'padding': '20px', 'fontFamily': 'sans-serif', 'minHeight': '100vh'}, children=[
    html.H2("Simulation Viewer", style={'textAlign': 'center', 'marginBottom': '0px', 'color': '#212529'}),

    dcc.Graph(id='live-map', style={'height': '750px'}),

    html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '20px', 'padding': '15px', 'backgroundColor': '#E9ECEF', 'borderRadius': '10px', 'border': '1px solid #DEE2E6'}, children=[

        html.Button("▶ Play / Pause", id='play-button', n_clicks=0, style={'padding': '10px 20px', 'fontSize': '16px', 'cursor': 'pointer', 'backgroundColor': '#007BFF', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold'}),

        html.Div(style={'flexGrow': '1'}, children=[
            dcc.Slider(
                id='time-slider',
                min=times[0] if times else 0,
                max=max_time,
                step=500,
                marks={str(t): {'label': str(t), 'style': {'color': '#495057'}} for t in times if t % 10000 == 0 or t == max_time},
                value=times[0] if times else 0
            )
        ]),

        html.Div(id='time-display', style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#007BFF', 'minWidth': '150px', 'textAlign': 'right'}),

        html.Div(style={'minWidth': '300px'}, children=[
            dcc.Dropdown(
                id='event-dropdown',
                options=event_options,
                placeholder="🔍 Jump to Transmission",
                style={'color': '#212529'}
            )
        ])
    ]),

    dcc.Interval(id='anim-interval', interval=800, n_intervals=0, disabled=True)
])
#=====================================================================


#==================================================================================================
# D] App Callbacks & Rendering Logic
#==================================================================================================

@app.callback(
    Output('anim-interval', 'disabled'),
    Input('play-button', 'n_clicks'),
    State('anim-interval', 'disabled')
)
def toggle_play(n_clicks, currently_disabled):
    return not currently_disabled if n_clicks > 0 else True

@app.callback(
    Output('time-slider', 'value'),
    [Input('anim-interval', 'n_intervals'), Input('event-dropdown', 'value')],
    State('time-slider', 'value')
)
def update_time(n_intervals, selected_event_time, current_time):
    trigger = ctx.triggered_id

    if trigger == 'event-dropdown' and selected_event_time is not None:
        return selected_event_time

    if not times:
        return 0

    closest_time = min(times, key=lambda x: abs(x - current_time))
    idx = times.index(closest_time)
    next_idx = (idx + 500) % len(times)
    return times[next_idx]

@app.callback(
    [Output('live-map', 'figure'), Output('time-display', 'children')],
    [Input('time-slider', 'value')]
)
def update_map(current_time):
    if times:
        current_time = min(times, key=lambda x: abs(x - current_time))
    fig = go.Figure()

    # 5.1 Static Semantic Layer
    fig.add_trace(go.Scatter(x=wall_x, y=wall_y, mode='lines', line=dict(color='#343A40', width=3), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=room_x, y=room_y, mode='text', text=room_names, textfont=dict(color='rgba(0, 0, 0, 0.15)', size=24, family="Arial Black"), hoverinfo='skip', showlegend=False))

    # 5.2 Dynamic Environmental Layer
    for d_id, coords in door_coords.items():
        fig.add_trace(go.Scatter(x=coords['x'], y=coords['y'], mode='lines', line=dict(color='#28A745', width=4, dash='dot'), hoverinfo='skip', showlegend=False))
    for i, b in enumerate(beds):
        fig.add_shape(type="rect", x0=b[0], y0=b[1], x1=b[2], y1=b[3], line=dict(color="#4169E1", width=2), fillcolor="rgba(65, 105, 225, 0.1)")

    # 5.3 Comet Trails
    history_df = df[(df['time'] <= current_time) & (df['time'] > current_time - 5000)]
    for aid in history_df['agent_id'].unique():
        adata = history_df[history_df['agent_id'] == aid].iloc[::50]

        # Patients get a subtle purple trail, Staff get standard grey
        trail_color = 'rgba(156, 39, 176, 0.4)' if aid.startswith('P') else 'rgba(100, 100, 100, 0.4)'

        fig.add_trace(go.Scatter(
            x=adata['pos_x'], y=adata['pos_y'], mode='lines',
            line=dict(color=trail_color, width=2, dash='solid'),
            hoverinfo='skip', showlegend=False
        ))

    # 5.4 Current Agent Positions
    current_df = df[df['time'] == current_time]
    # Custom Color Assignment
    agent_colors = []
    for aid, status in zip(current_df['agent_id'], current_df['infection_status']):
        if status == 2:
            agent_colors.append('#E32636') # Red if Infected
        elif str(aid).startswith('P'):
            agent_colors.append('#9C27B0') # Purple for Patient
        else:
            agent_colors.append('#1E90FF') # Blue for Healthcare Worker

    fig.add_trace(go.Scatter(
        x=current_df['pos_x'], y=current_df['pos_y'], mode='markers+text',
        marker=dict(
            size=14,
            color=agent_colors,
            line=dict(color='white', width=1.5)
        ),
        text=[str(aid) for aid in current_df['agent_id']],
        textposition="top center",
        textfont=dict(color='#212529', size=12, family='Arial, bold'),
        hovertext=[f"Agent {aid}" for aid in current_df['agent_id']],
        hoverinfo='text', showlegend=False
    ))

    # 5.5 Event Markers
    current_events = df_events[df_events['time'] == current_time]
    if not current_events.empty:
        event_texts = [f"<b>⚠️ Transmission</b><br>A{row['infector']} ➔ A{row['infectee']}" for _, row in current_events.iterrows()]
        fig.add_trace(go.Scatter(
            x=current_events['pos_x'], y=current_events['pos_y'], mode='markers+text',
            marker=dict(size=35, color='#FFC107', symbol='star-triangle-up', line=dict(color='#D32F2F', width=3)),
            text=event_texts, textposition="bottom center",
            textfont=dict(color='#D32F2F', size=14, family='Arial, bold'),
            name="Transmission Event", hoverinfo='skip'
        ))

    # 5.6 Layout
    fig.update_layout(
        template="plotly_white",
        xaxis=dict(showgrid=False, zeroline=False, visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor='#FFFFFF',
        paper_bgcolor='#FFFFFF'
    )

    return fig, f"Time: {current_time}s"
#==================================================================================================

#==================================================================================================
# Launch Server
#==================================================================================================
if __name__ == '__main__':
    print("🚀 Launching Viewer backend")
    app.run(debug=True, port=8080)
