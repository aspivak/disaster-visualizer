# Disaster Event Visualizer

A web application for visualizing disaster events and weather warnings on an interactive map.

## Features

- 🗺️ Interactive map with location search
- 🌍 Real-time disaster data from EONET, GDACS, and MeteoAlarm
- 📍 Filter by country and event type
- ✏️ Edit and view polygons in WKT format
- 📅 Date-based event filtering

## Data Sources

- **NASA EONET**: Natural disaster events
- **GDACS**: Global Disaster Alert and Coordination System
- **MeteoAlarm**: European weather warnings

## Local Development

### Prerequisites

- Python 3.11+
- pip

### Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python app.py
   ```

4. Open browser to `http://localhost:5000`

### Usage

1. Enter a date or use location search
2. Click "Fetch Data" to load disaster events
3. Select country and event type to view polygons
4. Edit polygons directly on the map or in the WKT field

## Deployment

### Deploy to Render

1. Push code to GitHub
2. Create account on [Render](https://render.com)
3. Create new Web Service
4. Connect your repository
5. Render will auto-detect `render.yaml` and deploy

### Manual Deployment

Set environment variable:
- `PORT`: Server port (default: 5000)

Build command:
```bash
pip install -r requirements.txt
```

Start command:
```bash
python app.py
```

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript
- **Map**: Leaflet.js
- **Geocoding**: Nominatim (OpenStreetMap)

## License

MIT
