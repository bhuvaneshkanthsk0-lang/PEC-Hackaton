from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from PIL import Image
import io
import database
import google.generativeai as genai
import json

app = Flask(__name__)
CORS(app)

database.init_db()

genai.configure(api_key="AIzaSyCm0ChcV1sN-TEUyGJ6i_hJ7y6jJ576msQ")
gemini_model = genai.GenerativeModel('gemini-3.6-flash')

MAP_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CleanWatch - Authority Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body { margin: 0; padding: 0; font-family: sans-serif; background: #0f172a; color: #f8fafc; }
        #map { height: 100vh; width: 100%; }
        .leaflet-popup-content { color: #0f172a; font-size: 14px; }
        .highlight { color: #16a34a; font-weight: bold; }
        .legend { background: white; padding: 10px; border-radius: 5px; color: black; position: absolute; bottom: 30px; right: 10px; z-index: 1000; box-shadow: 0 0 15px rgba(0,0,0,0.2); font-size: 0.9rem; }
    </style>
</head>
<body>
    <div id="map"></div>
    
    <div class="legend">
        📍 <b style="color: blue;">Blue Pins:</b> Recycling & Scrap Hubs<br>
        📍 <b style="color: red;">Red Pins:</b> Reported Waste
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const map = L.map('map').setView([13.0827, 80.2707], 12);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap'
        }).addTo(map);

        const hubIcon = L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
        });

        const wasteIcon = L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
        });

        async function fetchNearbyHubs(lat, lon) {
            const query = `[out:json];(node(around:10000, ${lat}, ${lon})["amenity"="recycling"];node(around:10000, ${lat}, ${lon})["shop"="scrap"];);out;`;
            const url = `https://overpass-api.de/api/interpreter?data=${encodeURIComponent(query)}`;

            try {
                const response = await fetch(url);
                const data = await response.json();
                
                data.elements.forEach(hub => {
                    const hubName = hub.tags.name || 'Local Scrap/Recycling Dealer';
                    L.marker([hub.lat, hub.lon], {icon: hubIcon})
                        .addTo(map)
                        .bindPopup(`<b>♻️ ${hubName}</b><br>Verified Hub`);
                });
            } catch (error) {
                console.error("Failed to load hubs:", error);
            }
        }

        async function loadMarkers() {
            try {
                const response = await fetch('/api/map-data');
                const data = await response.json();
                
                if (data.length === 0) return;

                data.forEach(report => {
                    const popupText = `
                        <b>Item:</b> ${report.item_type.toUpperCase()}<br>
                        <b>Value:</b> <span class="highlight">₹${report.estimated_value}</span><br>
                        <b>Time:</b> ${report.timestamp}
                    `;
                    L.marker([report.latitude, report.longitude], {icon: wasteIcon})
                        .addTo(map)
                        .bindPopup(popupText);
                });

                const latest = data[data.length - 1];
                map.setView([latest.latitude, latest.longitude], 13);
                fetchNearbyHubs(latest.latitude, latest.longitude);

            } catch (error) {
                console.error("Error loading map data:", error);
            }
        }

        loadMarkers();
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "CleanWatch AI Backend is running."})

@app.route("/map", methods=["GET"])
def view_map():
    return render_template_string(MAP_TEMPLATE)

@app.route("/api/map-data", methods=["GET"])
def get_map_data():
    try:
        data = database.get_all_reports()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user-summary", methods=["GET"])
def user_summary():
    try:
        reports = database.get_all_reports()
        total_items = len(reports)
        total_value = sum(float(report["estimated_value"]) for report in reports)
        
        return jsonify({
            "total_items": total_items,
            "total_value": round(total_value, 2),
            "history": reports
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/detect", methods=["POST"])
def detect_waste():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    try:
        image_file = request.files["image"]
        image = Image.open(io.BytesIO(image_file.read())).convert("RGB")
        
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        user_id = request.form.get("user_id", "guest_user")

        prompt = """
        Analyze this image carefully. Identify the main object being held, shown, or focused on in the foreground (such as paper, notebooks, books, electronics, plastics, metals, glass, fabric, or any other material). 
        Determine its material type and estimate a reasonable scrap or recycling value in INR based on standard Indian rates. 
        If an object is present in the foreground, you MUST classify it and give it a value—do not return zero items unless the image is completely blank or blurry.
        Return ONLY a valid JSON object in this exact format, with no markdown formatting or extra text:
        {
            "items_found": [{"item": "paper notebook", "estimated_value": 10.0, "confidence": 0.95}],
            "total_items": 1,
            "total_value": 10.0
        }
        """

        response = gemini_model.generate_content([prompt, image])
        
        response_text = response.text.strip().replace('```json', '').replace('```', '')
        ai_data = json.loads(response_text)

        detected_items = []
        total_estimated_value = 0.0

        for item in ai_data.get("items_found", []):
            item_name = item.get("item", "")
            if item_name.lower() != "not waste":
                item_value = float(item.get("estimated_value", 0.0))
                total_estimated_value += item_value
                
                detected_items.append({
                    "item": item_name,
                    "confidence": float(item.get("confidence", 0.99)),
                    "estimated_value": item_value
                })

                database.log_scan(
                    user_id=user_id,
                    item_type=item_name,
                    estimated_value=item_value,
                    lat=latitude,
                    lon=longitude
                )

        return jsonify({
            "status": "success",
            "total_items": len(detected_items),
            "total_value": round(total_estimated_value, 2),
            "detections": detected_items
        })

    except json.JSONDecodeError:
        return jsonify({"error": "AI response formatting error. Please try scanning again."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
