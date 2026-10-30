# AgriFlow — Farm Irrigation Network Optimizer

A responsive, full-stack academic project for modeling a farm's irrigation network, running graph algorithms, and drafting irrigation schedules.

## Technology
- **Python + Flask**: backend routes and application logic
- **SQLite**: persistent local database (created automatically)
- **HTML, CSS, JavaScript**: interactive dashboard
- **Java**: standalone Kruskal MST reference implementation in `java/GraphOptimizer.java`

## Features
- Professional responsive dashboard with farm network visualization
- Create/delete network nodes (source, field, pump, valve, tank)
- Create/delete pipeline edges with length, capacity, estimated loss and terrain factor
- **Kruskal MST**: selects a minimum spanning tree using terrain-weighted edge ordering; reports physical selected pipe length and disconnected components
- **Dijkstra shortest routes**: uses length, terrain factor, and uphill elevation penalty
- Irrigation scheduling heuristic based on field water-demand input, with morning/evening slots
- Mark scheduled work completed/reopen it; clear schedules
- Crop demand chart, network connectivity insight, CSV schedule export and network JSON export
- JSON API endpoints: `/api/network`, `/health`

## Run on Windows (VS Code)
1. Extract the ZIP.
2. Open the extracted `Farm_Irrigation_Network_Project` folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Create a virtual environment:
   ```bat
   py -m venv .venv
   ```
5. Install requirements:
   ```bat
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
6. Start the server:
   ```bat
   .venv\Scripts\python.exe app.py
   ```
7. Open `http://127.0.0.1:5000` in your browser.

The first run creates `irrigation.db` and inserts demo nodes and pipes. No MySQL setup is required.

## Java algorithm
Requires a JDK (Java 17 or later recommended):
```bat
cd java
javac GraphOptimizer.java
java GraphOptimizer
```

## Algorithm notes / academic scope
- A spanning tree only exists across all nodes if the graph is connected. The dashboard reports component count if it is disconnected.
- MST is an infrastructure-length approximation. The implementation orders edges by `length × terrain_factor`, while displaying the sum of physical lengths of chosen edges. For a formal minimum-length MST, use `length` alone as the edge weight; terrain-aware routing can be modeled as a separate objective.
- Dijkstra edge cost is `length × terrain_factor + 2 × positive uphill elevation difference`. This is a demonstrative cost model, not a hydraulic simulation.
- Scheduling is a heuristic demonstration. It does not fetch live weather, measure soil moisture, or operate real pumps. Validate any real-world design with hydraulic engineering and local agronomy data.
- Default demo values are illustrative. Replace them with measured farm data before reporting performance.

## Suggested performance analysis for your report
Compare:
1. Baseline: all entered pipeline links.
2. Kruskal MST: total physical pipe length, selected edge count, and connectivity.
3. Dijkstra: weighted route cost from selected source to each node.
4. Schedule heuristic: total daily water demand, number of fields served, and duration distribution.

Complexity: Kruskal is `O(E log E)` due to edge sorting (with near-constant amortized union-find operations); Dijkstra with a binary heap is `O((V + E) log V)`. Here `V` is node count and `E` is pipeline count.
