import threading
import requests
import json
import matplotlib.pyplot as plt
import numpy as np
import random
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

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

class TownMapApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EarthMC Plutonium Map")
        self.geometry("1200x800")
        self.configure(bg='#1e1e1e')

        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.configure_styles()

        self.slider_value = 250  

        self.create_widgets()
        self.town_data = None

    def configure_styles(self):
        self.style.configure('TFrame', background='#1e1e1e')
        self.style.configure('TLabel', background='#1e1e1e', foreground='#ffffff', font=('Helvetica', 12))
        self.style.configure('TEntry', fieldbackground='#2c2c2c', foreground='#ffffff', font=('Helvetica', 12))
        self.style.configure('TButton', font=('Helvetica', 12, 'bold'), background='#4CAF50', foreground='#ffffff')
        self.style.configure('TCheckbutton', background='#1e1e1e', foreground='#ffffff', font=('Helvetica', 12))
        self.style.map('TCheckbutton', background=[('active', '#1e1e1e')])

        self.style.configure('Generate.TButton', background='#4CAF50', foreground='#ffffff')
        self.style.map('Generate.TButton', 
                       background=[('active', '#45a049'), ('pressed', '#3d8b40')],
                       foreground=[('pressed', '#ffffff')])

    def create_widgets(self):
        self.main_frame = ttk.Frame(self, padding="20")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        ttk.Label(self.main_frame, text="Plutonium Map", font=('Helvetica', 24, 'bold'), foreground='#4CAF50').grid(row=0, column=0, columnspan=2, pady=(0, 20))

        self.create_input_frame()
        self.create_map_frame()

    def create_input_frame(self):
        input_frame = ttk.Frame(self.main_frame, padding="10")
        input_frame.grid(row=1, column=0, sticky='nsew')

        ttk.Label(input_frame, text="Nation Name(s):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.nation_entry = ttk.Entry(input_frame, width=30)
        self.nation_entry.grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(input_frame, text="Individual Town(s):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.town_entry = ttk.Entry(input_frame, width=30)
        self.town_entry.grid(row=1, column=1, sticky=tk.W, pady=5)

        self.show_home_blocks = tk.BooleanVar(value=True)
        self.home_blocks_check = ttk.Checkbutton(input_frame, text="Show Home Blocks", variable=self.show_home_blocks, command=self.update_map)
        self.home_blocks_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)

        self.color_mode = tk.StringVar(value='random')
        ttk.Label(input_frame, text="Color Mode:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.color_mode_combo = ttk.Combobox(input_frame, textvariable=self.color_mode, 
                                         values=['No Colors', 'random', 'numResidents', 'numTownBlocks', 'numOutlaws', 'numTrusted', 'Overclaimable', 'Population Density', 'Snipeable'], 
                                         state='readonly')
        self.color_mode_combo.grid(row=3, column=1, sticky=tk.W, pady=5)
        self.color_mode_combo.bind('<<ComboboxSelected>>', lambda e: self.update_map())

        ttk.Label(input_frame, text="Homeblock Star Size:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.star_size_slider = ttk.Scale(input_frame, from_=50, to=500, orient=tk.HORIZONTAL)
        self.star_size_slider.set(self.slider_value)  
        self.star_size_slider.grid(row=4, column=1, sticky=tk.W, pady=5)
        self.star_size_slider.bind('<ButtonRelease-1>', self.on_slider_release)  

        self.generate_button = ttk.Button(input_frame, text="Generate Map", command=self.run_generate_map_thread, style='Generate.TButton')
        self.generate_button.grid(row=5, column=0, columnspan=2, pady=10)

    def create_map_frame(self):
        self.map_frame = ttk.Frame(self.main_frame, padding="10")
        self.map_frame.grid(row=1, column=1, sticky='nsew')
        self.map_frame.columnconfigure(0, weight=1)
        self.map_frame.rowconfigure(0, weight=1)

    def update_map(self):
        if self.town_data is None:
            return

        star_size = self.slider_value  

        fig = gentownsmap(self.town_data, show_home_blocks=self.show_home_blocks.get(), 
                          color_mode=self.color_mode.get(), star_size=star_size)

        for widget in self.map_frame.winfo_children():
            widget.destroy()

        canvas = FigureCanvasTkAgg(fig, master=self.map_frame)
        canvas.draw()

        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=0, column=0, sticky='nsew')

        def on_resize(event):
            width, height = event.width, event.height
            fig.set_size_inches(width/fig.dpi, height/fig.dpi)
            canvas.draw()

        self.map_frame.bind("<Configure>", on_resize)

        self.update_idletasks()  

    def run_generate_map_thread(self):
        threading.Thread(target=self.generate_map, daemon=True).start()

    def generate_map(self):
        nation_names = self.nation_entry.get()
        town_names = self.town_entry.get()
        
        if not nation_names and not town_names:
            self.after(0, lambda: messagebox.showwarning("Input Error", "Please enter either nation names or individual town names."))
            return

        nation_towns = get_nation_towns(nation_names) if nation_names else []
        town_names_list = [name.strip() for name in town_names.split(',')] if town_names else []
        all_town_names = nation_towns + town_names_list

        if not all_town_names:
            self.after(0, lambda: messagebox.showwarning("Data Error", "No valid town names found."))
            return

        self.town_data = get_town_data(all_town_names)

        self.after(0, self.update_map)

    def on_slider_release(self, event):
        self.slider_value = self.star_size_slider.get()
        self.update_map()

    def on_resize(self, event):
        self.update_map()

if __name__ == "__main__":
    app = TownMapApp()
    app.mainloop()
