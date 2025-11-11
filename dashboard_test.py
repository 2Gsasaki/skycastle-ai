import pandas as pd
from dashboard import render_observation_form

df = pd.DataFrame([
    {"date": "2025-10-28", "temp": 9.575, "humidity": 90.25, "wind": 6.55, "cloud": 66.0, "rain": 0.175, "fog_observed": 0, "castle_visible": 0, "note": ""},
    {"date": "2025-10-29", "temp": 7.75, "humidity": 78.75, "wind": 1.0, "cloud": 11.5, "rain": 0.0, "fog_observed": 1, "castle_visible": 1, "note": ""},
])
print(df)
