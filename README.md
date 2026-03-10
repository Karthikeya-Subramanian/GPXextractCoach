# GPX Workout Analyzer

A lightweight **local web application** built with **Streamlit** to parse, segment, and visualize **GPX files from Strava and Garmin**.

This tool is designed for **runners and cyclists** who want granular insights into their structured workouts. It extracts telemetry data (GPS, heart rate, cadence) and calculates accurate lap averages without the GPS smoothing distortions found in many commercial platforms.

---

# Features

* **Dynamic Segmentation**

  * Split workouts into custom intervals by **distance (km)** or **time (minutes)**.

* **True Pace / Speed Calculation**

  * Uses **total distance ÷ total time** per interval instead of noisy instantaneous pace.

* **Dual Activity Profiles**

  * **Running** → pace in **min/km** with full-step cadence
  * **Cycling** → speed in **km/h**

* **Granular Lap Details**

  * Expand intervals to view **1-km or 1-minute sub-segments**.

* **Telemetry Visualizations**

  * Interactive **Plotly charts** showing:
  * pace / speed
  * heart rate
  * cadence

* **Robust Parsing**

  * Handles **missing GPX tags gracefully**
  * Suppresses unnecessary **Pandas / Streamlit warnings**

---

# Installation

## 1. Clone the Repository

```bash
git clone https://github.com/yourusername/gpx-workout-analyzer.git
cd gpx-workout-analyzer
```

## 2. Install Dependencies

Make sure **Python 3.9+** is installed.

```bash
pip install streamlit gpxpy pandas plotly numpy fpdf
```

(Optional)

```bash
pip install -r requirements.txt
```

---

# Usage

Run the application with:

```bash
streamlit run main.py
```

Streamlit will automatically launch the app in your default browser.

---

# How to Use

1. Export a **GPX file** from **Strava or Garmin**.
2. Upload the `.gpx` file in the app interface.
3. Select the activity type:

   * Running
   * Cycling
4. Choose interval segmentation:

   * Distance (e.g., 1 km splits)
   * Time (e.g., 5 minute intervals)
5. View:

   * Interval summaries
   * Pace / speed charts
   * Heart rate trends
   * Cadence data

---

# Example Use Cases

* Analyze **tempo runs**
* Review **interval workouts**
* Study **heart rate drift**
* Inspect **cadence consistency**
* Break down **long rides or runs into effort blocks**

---

# Project Structure

```
gpx-workout-analyzer
│
├── main.py               # Streamlit app entry point
├── README.md
│
└── screenshots
    ├── dashboard_run.png
    └── dashboard_cycle.png
```

---

# Data Privacy

This application runs **entirely locally**.

* GPX files are processed **only on your machine**
* No uploads to external servers
* No analytics or tracking

Your workout data **remains completely private**.

---

# Contributing

Contributions are welcome.

1. Fork the repository
2. Create a new branch

```bash
git checkout -b feature-name
```

3. Commit changes

```bash
git commit -m "Add new feature"
```

4. Push to your branch

```bash
git push origin feature-name
```

5. Open a Pull Request.

---

# License

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the **Software**), to deal in the Software without restriction, including without limitation the rights to:

* use
* copy
* modify
* merge
* publish
* distribute
* sublicense
* sell copies of the Software

and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED **"AS IS"**, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF:

* MERCHANTABILITY
* FITNESS FOR A PARTICULAR PURPOSE
* NONINFRINGEMENT

IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY ARISING FROM THE USE OF THIS SOFTWARE.
