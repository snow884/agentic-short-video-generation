import os

import requests

def generate_google_map_png(lat, lng, zoom=15, size="600x400", filename="map_with_marker.png"):
    # API Endpoint
    base_url = "https://maps.googleapis.com/maps/api/staticmap"
    
    # Parameters for the map and marker
    # 'markers' parameter format: color:LABEL|lat,lng
    params = {
        "center": f"{lat},{lng}",
        "zoom": zoom,
        "size": size,
        "maptype": "roadmap",
        "markers": f"color:red|label:S|{lat},{lng}",
        "key": os.getenv("MAP_API_KEY"),
        "format": "png"
    }

    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"Image saved as {filename}")
    else:
        print(f"Error: {response.status_code}, {response.text}")
