from flask import Flask, render_template, request, jsonify, send_file
import subprocess
import os
import json

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
        
    # Run the python script
    # Ensure date is in YYYYMMDD format if it comes as YYYY-MM-DD
    date = date.replace('-', '')
    
    try:
        # Calling python3 disaster_polygons.py --start_date [DATE]
        # Using subprocess to run the script
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
    # Get port from environment variable (for deployment platforms)
    port = int(os.environ.get('PORT', 5000))
    # Run on all interfaces for deployment
    app.run(host='0.0.0.0', port=port, debug=False)
