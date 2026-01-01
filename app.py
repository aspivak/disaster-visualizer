from flask import Flask, render_template, request, jsonify, send_file
import subprocess
import os
import json
import requests
from datetime import datetime
import re

app = Flask(__name__, template_folder='.')

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/run_script', methods=['POST'])
def run_script():
    data = request.json
    date = data.get('date')
    
    if not date:
        return jsonify({"error": "Date is required"}), 400
        
    date = date.replace('-', '')
    
    try:
        result = subprocess.run(
            ['python3', 'disaster_polygons.py', '--start_date', date],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        
        if result.returncode != 0:
            return jsonify({"error": f"Script failed: {result.stderr}"}), 500
            
        return jsonify({"message": "Script executed successfully", "output": result.stdout})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/search_gemini', methods=['POST'])
def search_gemini():
    """Search for crisis events using Gemini REST API."""
    from shapely.geometry import Point
    from shapely.wkt import dumps as wkt_dumps
    
    data = request.json
    date = data.get('date')
    api_key = data.get('api_key')
    custom_prompt = data.get('prompt', '')
    
    if not date:
        return jsonify({"error": "Date is required"}), 400
    
    if not api_key:
        return jsonify({"error": "Gemini API key is required"}), 400
    
    try:
        dt = datetime.strptime(date, '%Y-%m-%d')
        readable_date = dt.strftime('%B %d, %Y')
        
        # Use Gemini REST API v1 with gemini-2.5-flash model
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        # Use custom prompt if provided, otherwise use default
        if custom_prompt:
            prompt = custom_prompt.replace('{date}', readable_date).replace('{date_compact}', date.replace('-', ''))
        else:
            prompt = f"""Search for disaster and crisis-related events on {readable_date}.
Include: natural disasters, severe weather, conflicts, major accidents.
Return JSON: {{"events": [{{"event_name": "name", "location": "city", "country": "country", 
"description": "brief", "estimated_lat": 0.0, "estimated_lon": 0.0}}]}}"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        gemini_response = response.json()
        
        # Extract text from Gemini response
        try:
            response_text = gemini_response['candidates'][0]['content']['parts'][0]['text'].strip()
        except (KeyError, IndexError):
            return jsonify({"error": "Invalid Gemini API response"}), 500
        
        # Parse JSON from response
        # Parse JSON from response
        # Using a more robust regex to find the JSON object
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            json_str = json_match.group()
            
            # Sanitization: Fix double curly braces if present (LLM artifact)
            # Replaces {{ with { and }} with }
            # But we must be careful not to break valid use cases? 
            # In JSON structure context, double braces are invalid, so it's safe to replace them
            if '{{' in json_str:
                json_str = json_str.replace('{{', '{').replace('}}', '}')
                
            try:
                events_data = json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    # Try to clean up markdown code blocks if present
                    clean_text = response_text.replace('```json', '').replace('```', '').strip()
                    if '{{' in clean_text:
                         clean_text = clean_text.replace('{{', '{').replace('}}', '}')
                    events_data = json.loads(clean_text)
                except json.JSONDecodeError:
                    # Fallback: Try parsing as Python literal (handles single quotes)
                    try:
                        import ast
                        events_data = ast.literal_eval(json_str)
                    except:
                        # Final attempt: manual cleanup of single quotes
                        try:
                            # Naive replacement of single quotes to double quotes just for keys
                            fixed_json = re.sub(r"'(.*?)':", r'"\1":', json_str)
                            fixed_json = fixed_json.replace("':", '":').replace(", '", ', "').replace("{ '", '{ "')
                            events_data = json.loads(fixed_json)
                        except:
                            return jsonify({"error": "Failed to parse Gemini JSON response", "raw": response_text}), 500
        else:
            try:
                events_data = json.loads(response_text)
            except:
                return jsonify({"error": "Invalid JSON format from Gemini", "raw": response_text}), 500
            
        # If the result is already in the target structure (nested dictionary)
        # We can detect this by checking if it has keys that look like our expected structure
        # The new prompt returns { "YYYYMMDD": ... }
        date_key = date.replace('-', '')
        if date_key in events_data:
             # It's the new nested structure, return it directly
             return jsonify(events_data)
        
        # Legacy parsing for flat "events" list
        results = []
        for event in events_data.get('events', []):
            try:
                lat = float(event.get('estimated_lat', 0))
                lon = float(event.get('estimated_lon', 0))
                
                point = Point(lon, lat)
                polygon = point.buffer(0.5)
                wkt = wkt_dumps(polygon)
                
                results.append({
                    'date': date.replace('-', ''),
                    'country': event.get('country', 'Unknown'),
                    'event': f"{event.get('event_name')} - {event.get('description', '')}",
                    'polygon': wkt
                })
            except:
                continue
        
        return jsonify({"events": results, "count": len(results)})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Gemini API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/results', methods=['GET'])
def get_results():
    if not os.path.exists('results.json'):
        return jsonify({})
    
    try:
        with open('results.json', 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
