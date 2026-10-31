from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3, os, math, heapq, json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "irrigation.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "farm-irrigation-dev-key-change-me")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS nodes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      kind TEXT NOT NULL DEFAULT 'Field', crop TEXT DEFAULT 'Mixed crops',
      water_need REAL NOT NULL DEFAULT 10, elevation REAL NOT NULL DEFAULT 0,
      x REAL NOT NULL DEFAULT 0, y REAL NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS pipes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL,
      target_id INTEGER NOT NULL, length REAL NOT NULL, capacity REAL NOT NULL DEFAULT 30,
      loss_rate REAL NOT NULL DEFAULT 2, terrain_factor REAL NOT NULL DEFAULT 1,
      FOREIGN KEY(source_id) REFERENCES nodes(id), FOREIGN KEY(target_id) REFERENCES nodes(id)
    );
    CREATE TABLE IF NOT EXISTS schedules(
      id INTEGER PRIMARY KEY AUTOINCREMENT, node_id INTEGER NOT NULL,
      day TEXT NOT NULL, start_time TEXT NOT NULL, duration REAL NOT NULL,
      volume REAL NOT NULL, status TEXT NOT NULL DEFAULT 'Planned',
      FOREIGN KEY(node_id) REFERENCES nodes(id)
    );
    """)
    count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    if count == 0:
        nodes = [
            ("Main Reservoir", "Source", "—", 0, 112, 10, 50),
            ("North Field", "Field", "Wheat", 18, 108, 35, 20),
            ("East Orchard", "Field", "Apple", 24, 116, 70, 43),
            ("Greenhouse", "Field", "Vegetables", 12, 110, 58, 76),
            ("South Field", "Field", "Cotton", 30, 101, 30, 82),
            ("Pump Station", "Pump", "—", 0, 105, 18, 58),
        ]
        conn.executemany("INSERT INTO nodes(name,kind,crop,water_need,elevation,x,y) VALUES(?,?,?,?,?,?,?)", nodes)
        pipes = [
            (1,2,120,35,1.5,1.1),(1,6,55,50,1.0,1.0),(6,5,95,30,2.0,1.3),
            (6,4,105,25,1.7,1.1),(2,5,88,20,2.5,1.2),(2,3,90,22,2.0,1.0),
            (3,4,65,20,1.2,1.1),(5,4,115,18,2.8,1.4),(1,3,165,30,2.1,1.0)
        ]
        conn.executemany("INSERT INTO pipes(source_id,target_id,length,capacity,loss_rate,terrain_factor) VALUES(?,?,?,?,?,?)", pipes)
    conn.commit()
    conn.close()

def rows(query, params=()):
    conn = db()
    result = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in result]

def get_graph():
    nodes = rows("SELECT * FROM nodes ORDER BY id")
    pipes = rows("""SELECT p.*, a.name AS source_name, b.name AS target_name,
                    a.elevation AS source_elevation, b.elevation AS target_elevation
                    FROM pipes p JOIN nodes a ON p.source_id=a.id JOIN nodes b ON p.target_id=b.id""")
    return nodes, pipes

def kruskal(nodes, pipes):
    parent = {n["id"]: n["id"] for n in nodes}
    rank = {n["id"]: 0 for n in nodes}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a,b):
        ra, rb = find(a), find(b)
        if ra == rb: return False
        if rank[ra] < rank[rb]: ra,rb=rb,ra
        parent[rb] = ra
        if rank[ra] == rank[rb]: rank[ra] += 1
        return True
    chosen, total = [], 0
    for p in sorted(pipes, key=lambda x: x["length"] * x["terrain_factor"]):
        if union(p["source_id"], p["target_id"]):
            chosen.append(p)
            total += p["length"]
    components = len({find(n["id"]) for n in nodes})
    return chosen, round(total,2), components

def dijkstra(nodes, pipes, start_id):
    graph = {n["id"]: [] for n in nodes}
    for p in pipes:
        # Effective cost blends pipe length, elevation climb, and terrain difficulty.
        a, b = p["source_id"], p["target_id"]
        climb = max(0, p["target_elevation"] - p["source_elevation"])
        cost = p["length"] * p["terrain_factor"] + climb * 2
        graph[a].append((b, cost, p))
        graph[b].append((a, cost, p))
    dist = {n["id"]: float("inf") for n in nodes}
    prev = {}
    dist[start_id] = 0
    heap = [(0,start_id)]
    while heap:
        d,u = heapq.heappop(heap)
        if d != dist[u]: continue
        for v,w,p in graph[u]:
            if d+w < dist[v]:
                dist[v] = d+w
                prev[v] = (u,p)
                heapq.heappush(heap,(d+w,v))
    paths = {}
    names = {n["id"]:n["name"] for n in nodes}
    for n in nodes:
        target=n["id"]
        if dist[target] == float("inf"):
            paths[target]={"reachable":False,"cost":None,"route":[]}
            continue
        route=[target]; cur=target
        while cur != start_id and cur in prev:
            cur=prev[cur][0]; route.append(cur)
        route.reverse()
        paths[target]={"reachable":True,"cost":round(dist[target],2),"route":[names[i] for i in route]}
    return paths

def make_schedule(nodes):
    fields=[n for n in nodes if n["kind"].lower() == "field"]
    # Water-efficient night/early morning slots; higher-demand crops get longer duration.
    slots=[("05:00", "Morning"),("06:30","Morning"),("18:00","Evening"),("19:30","Evening")]
    result=[]
    for i,n in enumerate(sorted(fields,key=lambda x:x["water_need"], reverse=True)):
        duration=round(max(0.5,n["water_need"]/8),1)
        start,period=slots[i % len(slots)]
        result.append({"node_id":n["id"],"name":n["name"],"crop":n["crop"],"water_need":n["water_need"],
                       "start_time":start,"period":period,"duration":duration,
                       "volume":round(n["water_need"]*1000,0)})
    return result

@app.route("/")
def dashboard():
    nodes,pipes=get_graph()
    mst,total,components=kruskal(nodes,pipes)
    source=next((n for n in nodes if n["kind"].lower()=="source"), nodes[0] if nodes else None)
    paths=dijkstra(nodes,pipes,source["id"]) if source else {}
    fields=[n for n in nodes if n["kind"].lower()=="field"]
    total_need=sum(n["water_need"] for n in fields)
    avg_loss=sum(p["loss_rate"] for p in pipes)/len(pipes) if pipes else 0
    schedules=rows("""SELECT s.*,n.name AS node_name FROM schedules s JOIN nodes n ON s.node_id=n.id
                      ORDER BY s.day,s.start_time LIMIT 8""")
    return render_template("dashboard.html",nodes=nodes,pipes=pipes,mst=mst,total=total,
        components=components,paths=paths,source=source,fields=fields,total_need=round(total_need,1),
        avg_loss=round(avg_loss,2),schedules=schedules,now=datetime.now().strftime("%d %b %Y"))

@app.route("/nodes/add", methods=["POST"])
def add_node():
    name=request.form.get("name","").strip()
    kind=request.form.get("kind","Field")
    crop=request.form.get("crop","Mixed crops").strip() or "Mixed crops"
    try:
        water=float(request.form.get("water_need",0)); elevation=float(request.form.get("elevation",0))
        x=float(request.form.get("x",50)); y=float(request.form.get("y",50))
        if not name: raise ValueError("Node name is required.")
        if water < 0: raise ValueError("Water requirement cannot be negative.")
        conn=db(); conn.execute("INSERT INTO nodes(name,kind,crop,water_need,elevation,x,y) VALUES(?,?,?,?,?,?,?)",
            (name,kind,crop,water,elevation,x,y)); conn.commit(); conn.close()
        flash(f'{name} added to the network.', 'success')
    except ValueError as e: flash(str(e) or "Enter valid numeric values.",'error')
    return redirect(url_for("dashboard")+"#network")

@app.route("/nodes/<int:node_id>/delete", methods=["POST"])
def delete_node(node_id):
    conn=db()
    conn.execute("DELETE FROM pipes WHERE source_id=? OR target_id=?",(node_id,node_id))
    conn.execute("DELETE FROM schedules WHERE node_id=?",(node_id,))
    conn.execute("DELETE FROM nodes WHERE id=?",(node_id,))
    conn.commit(); conn.close()
    flash("Node and its connected pipes removed.", "success")
    return redirect(url_for("dashboard")+"#network")

@app.route("/pipes/add", methods=["POST"])
def add_pipe():
    try:
        a=int(request.form["source_id"]); b=int(request.form["target_id"])
        length=float(request.form["length"]); capacity=float(request.form["capacity"])
        loss=float(request.form["loss_rate"]); terrain=float(request.form["terrain_factor"])
        if a==b: raise ValueError("A pipe must connect two different nodes.")
        if length<=0 or capacity<=0 or loss<0 or terrain<=0: raise ValueError("Length, capacity and terrain factor must be positive; loss cannot be negative.")
        conn=db()
        conn.execute("INSERT INTO pipes(source_id,target_id,length,capacity,loss_rate,terrain_factor) VALUES(?,?,?,?,?,?)",(a,b,length,capacity,loss,terrain))
        conn.commit(); conn.close(); flash("Pipeline connection added.", "success")
    except (ValueError, KeyError) as e: flash(str(e) or "Please enter valid pipeline values.", "error")
    return redirect(url_for("dashboard")+"#network")

@app.route("/pipes/<int:pipe_id>/delete", methods=["POST"])
def delete_pipe(pipe_id):
    conn=db(); conn.execute("DELETE FROM pipes WHERE id=?",(pipe_id,)); conn.commit(); conn.close()
    flash("Pipeline removed.", "success")
    return redirect(url_for("dashboard")+"#network")

@app.route("/optimize", methods=["POST"])
def optimize():
    nodes,pipes=get_graph()
    mst,total,components=kruskal(nodes,pipes)
    return jsonify({"success":True,"algorithm":"Kruskal Minimum Spanning Tree","total_length":total,
      "edges_selected":len(mst),"node_count":len(nodes),"components":components,
      "connected":components<=1,"edges":[{"from":p["source_name"],"to":p["target_name"],"length":p["length"],
      "weighted_cost":round(p["length"]*p["terrain_factor"],2),"loss_rate":p["loss_rate"]} for p in mst],
      "note":"MST minimizes the sum of physical pipe lengths weighted for terrain during edge selection. It does not model hydraulic pressure or guarantee zero water loss."})

@app.route("/route", methods=["POST"])
def route():
    try: start_id=int(request.form.get("start_id"))
    except (TypeError,ValueError): return jsonify({"success":False,"error":"Choose a valid starting water source."}),400
    nodes,pipes=get_graph()
    if not any(n["id"]==start_id for n in nodes): return jsonify({"success":False,"error":"Start node not found."}),404
    paths=dijkstra(nodes,pipes,start_id)
    byid={n["id"]:n["name"] for n in nodes}
    return jsonify({"success":True,"start":byid[start_id],"paths":[{"destination":byid[i],"reachable":v["reachable"],"cost":v["cost"],"route":v["route"]} for i,v in paths.items()]})

@app.route("/schedule/generate", methods=["POST"])
def generate_schedule():
    nodes,_=get_graph()
    plan=make_schedule(nodes)
    today=datetime.now().strftime("%Y-%m-%d")
    conn=db()
    conn.execute("DELETE FROM schedules WHERE day=?",(today,))
    conn.executemany("INSERT INTO schedules(node_id,day,start_time,duration,volume,status) VALUES(?,?,?,?,?,'Planned')",
      [(p["node_id"],today,p["start_time"],p["duration"],p["volume"]) for p in plan])
    conn.commit(); conn.close()
    return jsonify({"success":True,"date":today,"count":len(plan),"schedule":plan,
      "note":"Planning heuristic: higher-demand fields are scheduled first, using early-morning/evening slots to reduce evaporation. Verify against local weather, soil moisture, crop stage and actual flow rates."})

@app.route("/schedule/<int:schedule_id>/toggle", methods=["POST"])
def toggle_schedule(schedule_id):
    conn=db(); row=conn.execute("SELECT status FROM schedules WHERE id=?",(schedule_id,)).fetchone()
    if row:
        new="Completed" if row["status"]!="Completed" else "Planned"
        conn.execute("UPDATE schedules SET status=? WHERE id=?",(new,schedule_id)); conn.commit()
    conn.close()
    return redirect(url_for("dashboard")+"#schedule")

@app.route("/schedule/clear", methods=["POST"])
def clear_schedule():
    conn=db(); conn.execute("DELETE FROM schedules"); conn.commit(); conn.close()
    flash("All generated schedules cleared.", "success")
    return redirect(url_for("dashboard")+"#schedule")

@app.route("/api/network")
def api_network():
    nodes,pipes=get_graph()
    return jsonify({"nodes":nodes,"pipes":pipes})

@app.route("/health")
def health():
    return jsonify({"status":"ok","app":"Farm Irrigation Network Optimizer"})

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
