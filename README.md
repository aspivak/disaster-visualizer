# Disaster Event Visualizer

A serverless, pure frontend web application for visualizing disaster events and weather warnings on an interactive map.

## Overview

This application helps intelligence analysts and researchers visualize global crisis events by aggregating data from multiple sources and displaying them on an interactive map. It runs entirely in the browser using JavaScript.

## Features

- **🌍 Real-time Data**: Fetches events from NASA EONET and GDACS.
- **✨ AI Analysis**: Integrated Gemini API for analyzing global news for crisis events with strict temporal logic.
- **📍 Interactive Map**: Full-screen Leaflet map with geocoding search.
- **📂 Client-Side Architecture**: No backend server required – runs directly in the browser.
- **🎨 Modern UI**: Glass-morphism sidebar layout with intuitive controls.
- **🏷️ Event Classification**: 自動 Automatically groups events into categories like "Earthquake", "Fire", "Conflict", etc.
- **🧱 WKT Support**: View and edit Polygon WKT (Well-Known Text) directly.

## Usage

### Prerequisites
- A modern web browser (Chrome, Firefox, Safari, Edge).
- (Optional) A Google Gemini API Key for AI analysis features.

### Running the App
Since the application uses a pure frontend architecture, you can run it by simply opening the file:

1. Locate `index.html` in the project folder.
2. Double-click to open it in your browser.

*Note: For external API calls to work from a `file://` protocol, the application automatically uses a CORS proxy.*

### How to Use
1. **Target Date**: Select a date to investigate.
2. **Fetch Data**: Click "Fetch Live Data" to load events from EONET and GDACS.
3. **AI Analysis**: 
   - Open "Gemini Configuration".
   - Enter your API Key.
   - Click "Analysis with Gemini" to scan for high-impact events reported in the news.
4. **Filter & Explore**: 
   - Use the **Country** dropdown to select a region.
   - Use the **Event Type** dropdown to view specific categories (e.g., "Fire", "Flood").
   - Read the **Description** (auto-expands for long text).
   - View the event coverage polygon on the map.

## Tech Stack

- **Core**: HTML5, CSS3, JavaScript (ES6+)
- **Map**: Leaflet.js, Leaflet Draw
- **Geometry**: Wicket (for WKT parsing)
- **APIs**: 
  - NASA EONET (Natural Events)
  - GDACS (Disaster Alerts)
  - Gemini API (AI Analysis)
  - Nominatim (Geocoding)

## Project Structure

- `index.html` - Main application entry point and UI.
- `disaster-api.js` - Core logic for API fetching, data parsing, and geometry handling.
- `assets/` - Images and other static resources.

## Deployment

### Render (Static Site)
This project is configured for deployment on [Render](https://render.com) as a Static Site.
1. Push code to GitHub.
2. Link repository in Render.
3. Render will auto-detect `render.yaml` and deploy.

## License

MIT
