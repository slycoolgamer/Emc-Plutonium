import io
import base64
import threading
import requests
import json
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import random
import matplotlib.colors as mcolors
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

API_NATIONS = "https://api.earthmc.net/v3/aurora/nations"
API_TOWNS = "https://api.earthmc.net/v3/aurora/towns"
API_PLAYERS = "https://api.earthmc.net/v3/aurora/players"

def generate_color():
    return mcolors.to_hex(mcolors.hsv_to_rgb((random.random(), 0.7, 0.9)))

def gentownsmap(towns, show_home_blocks=True, color_mode='random', star_size=250):
    fig = Figure(figsize=(10, 10), facecolor='#1e1e1e')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#1e1e1e')

    all_x = []
    all_y = []
    for town in towns:
        town_blocks = town['coordinates']['townBlocks']
        x_vals, y_vals = zip(*town_blocks)
        all_x.extend(x_vals)
        all_y.extend(y_vals)

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    grid_width = max_x - min_x + 1
    grid_height = max_y - min_y + 1

    grid = np.zeros((grid_height, grid_width))
    colors = []

    if color_mode != 'random' and color_mode != 'Overclaimable' and color_mode != 'No Colors' and color_mode != 'Snipeable':
        if color_mode == 'Population Density':
            stat_values = [town['stats']['numResidents'] / max(town['stats']['numTownBlocks'], 1) for town in towns]
        elif color_mode == 'Days Since Last Online':
            current_time = int(time.time() * 1000)  # Current time in milliseconds
            stat_values = [(current_time - town['mayor_last_online']) / (24 * 60 * 60 * 1000) for town in towns]
        else:
            stat_values = [town['stats'][color_mode] for town in towns]
        log_stat_values = np.log1p(stat_values)
        min_stat, max_stat = min(log_stat_values), max(log_stat_values)

    current_time = int(time.time() * 1000)  # Current time in milliseconds
    ten_days_ms = 28 * 24 * 60 * 60 * 1000  # 10 days in milliseconds

    for town in towns:
        if color_mode == 'No Colors':
            color = '#ffffff'
        elif color_mode == 'random':
            color = generate_color()
        elif color_mode == 'Overclaimable':
            if town['status']['isOverClaimed'] and not town['status']['hasOverclaimShield']:
                color = 'red'
            else:
                color = 'grey'
        elif color_mode == 'Snipeable':
            if (town['stats']['numResidents'] == 1 and 
                town['status']['isOpen'] and 
                'mayor_last_online' in town and 
                current_time - town['mayor_last_online'] > ten_days_ms):
                color = 'yellow'
            else:
                color = 'grey'
        elif color_mode == 'Days Since Last Online':
            days_since_last_online = (current_time - town['mayor_last_online']) / (24 * 60 * 60 * 1000)
            log_stat_value = np.log1p(days_since_last_online)
            color_value = (log_stat_value - min_stat) / (max_stat - min_stat)
            color = plt.cm.viridis(color_value)
        else:
            if color_mode == 'Population Density':
                stat_value = town['stats']['numResidents'] / max(town['stats']['numTownBlocks'], 1)
            else:
                stat_value = town['stats'][color_mode]
            log_stat_value = np.log1p(stat_value)
            color_value = (log_stat_value - min_stat) / (max_stat - min_stat)
            color = plt.cm.viridis(color_value)

        colors.append(color)
        town_blocks = town['coordinates']['townBlocks']
        for x, y in town_blocks:
            grid[y - min_y, x - min_x] = len(colors)

    cmap = mcolors.ListedColormap(['#1e1e1e'] + colors)
    bounds = np.arange(len(colors) + 2) - 0.5
    norm = mcolors.BoundaryNorm(bounds, cmap.N)

    ax.clear() 
    c = ax.pcolormesh(np.arange(min_x, max_x + 2), np.arange(min_y, max_y + 2), grid, cmap=cmap, norm=norm, shading='auto')

    if show_home_blocks:
        for town in towns:
            home_block = town['coordinates']['homeBlock']
            ax.scatter(home_block[0], home_block[1], c='#4CAF50', marker='*', s=star_size, edgecolor='white', zorder=5)

    ax.set_aspect('equal')
    ax.axis('off')

    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title("", fontsize=16, fontweight='bold', color='#ffffff')
    ax.invert_yaxis()

    fig.tight_layout()

    return fig

def batch_requests(data_list, batch_size=100):
    for i in range(0, len(data_list), batch_size):
        yield data_list[i:i + batch_size]

def get_nation_towns(nation_names):
    headers = {"Content-Type": "application/json"}
    nations = [name.strip() for name in nation_names.split(',')]

    all_town_names = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_batch = {executor.submit(fetch_nation_batch, batch): batch for batch in batch_requests(nations, batch_size=100)}
        for future in as_completed(future_to_batch):
            all_town_names.extend(future.result())

    return all_town_names

def fetch_nation_batch(nation_batch):
    headers = {"Content-Type": "application/json"}
    content = {"query": nation_batch}
    response = requests.post(API_NATIONS, json=content, headers=headers)
    town_names = []
    if response.status_code == 200:
        nation_data = response.json()
        if nation_data:
            for nation in nation_data:
                town_names.extend([town['name'] for town in nation['towns']])
    return town_names

def get_town_data(town_names):
    headers = {"Content-Type": "application/json"}
    
    all_town_data = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_batch = {executor.submit(fetch_town_batch, batch): batch for batch in batch_requests(town_names, batch_size=100)}
        for future in as_completed(future_to_batch):
            all_town_data.extend(future.result())

    # Fetch mayor data for all towns
    mayor_names = [town['mayor']['name'] for town in all_town_data]
    mayor_data = get_player_data(mayor_names)

    # Add mayor last online timestamp to town data
    for town in all_town_data:
        mayor_name = town['mayor']['name']
        if mayor_name in mayor_data:
            town['mayor_last_online'] = mayor_data[mayor_name]['timestamps']['lastOnline']

    return all_town_data

def fetch_town_batch(town_batch):
    headers = {"Content-Type": "application/json"}
    content = {"query": town_batch}
    response = requests.post(API_TOWNS, json=content, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def get_player_data(player_names):
    headers = {"Content-Type": "application/json"}
    
    all_player_data = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_batch = {executor.submit(fetch_player_batch, batch): batch for batch in batch_requests(player_names, batch_size=100)}
        for future in as_completed(future_to_batch):
            all_player_data.update(future.result())

    return all_player_data

def fetch_player_batch(player_batch):
    headers = {"Content-Type": "application/json"}
    content = {"query": player_batch}
    response = requests.post(API_PLAYERS, json=content, headers=headers)
    player_data = {}
    if response.status_code == 200:
        data = response.json()
        for player in data:
            player_data[player['name']] = player
    return player_data

@app.route('/generate_map', methods=['POST'])
def generate_map_api():
    data = request.json
    nation_names = data.get('nation_names', '')
    town_names = data.get('town_names', '')
    show_home_blocks = data.get('show_home_blocks', True)
    color_mode = data.get('color_mode', 'random')
    star_size = data.get('star_size', 250)

    if not nation_names and not town_names:
        return jsonify({"error": "Please provide either nation names or individual town names."}), 400

    nation_towns = get_nation_towns(nation_names) if nation_names else []
    town_names_list = [name.strip() for name in town_names.split(',')] if town_names else []
    all_town_names = nation_towns + town_names_list

    if not all_town_names:
        return jsonify({"error": "No valid town names found."}), 400

    town_data = get_town_data(all_town_names)

    if not town_data:
        return jsonify({"error": "No valid town data found."}), 400

    try:
        fig = gentownsmap(town_data, show_home_blocks=show_home_blocks, 
                          color_mode=color_mode, star_size=star_size)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format='png', facecolor='#1e1e1e', edgecolor='none')
    img_buffer.seek(0)
    
    return send_file(img_buffer, mimetype='image/png')

if __name__ == "__main__":
    app.run(debug=True)
