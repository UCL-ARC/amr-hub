AMR-HUB door exploration

Runs inside the existing AMR JupyterLab image (amr-bc-jupyter-report); no rebuild needed.

Files
  AMR_HUB_Door_Exploration.ipynb        notebook: runs the extraction and shows the figures
  door_exploration_existing_jupyter.py  analysis code; also runs from the command line

Setup
  JupyterLab is rooted at /outputs. Copy both files into the host folder mounted at
  /outputs (e.g. $HOME/amr_outputs/) and open the notebook. The database is read from
  /data; set DB_NAME in the first cell if there is more than one database file.

Command line (JupyterLab terminal)
  python /outputs/door_exploration_existing_jupyter.py [--db FILE] [--door-dedupe-seconds N]

Outputs (/outputs/door_exploration/)
  shift_door_activity.csv, door_episodes.csv, door_counts.csv,
  door_transition_matrix.csv, door_exploration_summary.csv
  01_door_interactions_per_shift.svg
  02_door_interactions_per_hour.svg
  03_door_interactions_vs_shift_duration.svg
  04_minutes_between_door_interactions.svg
  05_activities_between_doors.svg
  06_door_transition_matrix.svg

Door messages are not deduplicated by default (--door-dedupe-seconds 0).
