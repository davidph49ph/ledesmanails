from flask import Flask, render_template, jsonify, request
import datetime
import os

# Forzar a Flask a encontrar la carpeta templates de forma absoluta en el servidor
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)

# --- BASE DE DATOS EN MEMORIA ---
brand_name = "LedesmaNails"
settings = {
    "default_shifts": [("09:00", "14:00"), ("16:00", "20:00")],
    "rounding_mins": 10,
    "global_fianza": False,
    "fianza_amount": 15.0,
    "welcome_msg": "¡Gracias por tu reserva en LedesmaNails! Tu cita está pendiente de confirmación. Te avisaremos enseguida."
}

services = [
    {"id": 1, "name": "Uñas Semipermanentes", "desc": "Manicura completa con esmaltado semipermanente de alta duración.", "price": 25.0, "duration": 60},
    {"id": 2, "name": "Uñas Acrigel", "desc": "Construcción y nivelación con acrigel premium. Ideal para extensiones.", "price": 50.0, "duration": 120},
    {"id": 3, "name": "Retirada + Gel X", "desc": "Retirada segura del material anterior y colocación de tips Gel X.", "price": 40.0, "duration": 90},
    {"id": 4, "name": "Manicura Básica", "desc": "Limpieza de cutículas, limado y brillo nutritivo.", "price": 15.0, "duration": 30}
]

extras = [
    {"id": 1, "name": "Francesa", "price": 5.0, "duration": 10, "active": True},
    {"id": 2, "name": "Efecto Cromado", "price": 8.0, "duration": 10, "active": True},
    {"id": 3, "name": "Decoración Sencilla", "price": 10.0, "duration": 15, "active": True},
    {"id": 4, "name": "Decoración Elaborada", "price": 20.0, "duration": 30, "active": True}
]

clients = {
    "666111222": {"name": "María", "surname": "García", "phone": "666111222", "email": "maria@mail.com", "fianza_obligatoria": False, "notes": "Prefiere tonos nude."}
}

appointments = [
    {
        "id": 1,
        "client_name": "María García",
        "client_phone": "666111222",
        "service_name": "Uñas Acrigel",
        "extras_names": ["Francesa"],
        "start_time": "11:00",
        "end_time": "13:10",
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "total_price": 55.0,
        "status": "Pendiente"
    }
]

custom_daily_hours = {}

# --- MOTOR DE CÁLCULO DE HUECOS INTELIGENTE (MULTI-TURNO) ---
def calculate_slots(date_str, needed_duration):
    shifts_raw = custom_daily_hours.get(date_str, settings["default_shifts"])
    day_shifts = []
    for s_str, e_str in shifts_raw:
        try:
            s_dt = datetime.datetime.strptime(f"{date_str} {s_str}", "%Y-%m-%d %H:%M")
            e_dt = datetime.datetime.strptime(f"{date_str} {e_str}", "%Y-%m-%d %H:%M")
            day_shifts.append((s_dt, e_dt))
        except ValueError:
            continue
            
    day_events = []
    for appt in appointments:
        if appt["date"] == date_str and appt["status"] not in ["Cancelada", "Rechazada"]:
            s = datetime.datetime.strptime(f"{date_str} {appt['start_time']}", "%Y-%m-%d %H:%M")
            e = datetime.datetime.strptime(f"{date_str} {appt['end_time']}", "%Y-%m-%d %H:%M")
            day_events.append((s, e))
            
    day_events.sort(key=lambda x: x[0])
    valid_slots = []
    
    for shift_start, shift_end in day_shifts:
        potential_starts = [shift_start]
        for s, e in day_events:
            if shift_start <= e <= shift_end:
                potential_starts.append(e)
                
        temp_time = shift_start
        while temp_time < shift_end:
            potential_starts.append(temp_time)
            temp_time += datetime.timedelta(minutes=30)
            
        potential_starts = sorted(list(set(potential_starts)))
        
        for start in potential_starts:
            end = start + datetime.timedelta(minutes=needed_duration)
            if end > shift_end:
                continue
                
            overlap = False
            for ev_start, ev_end in day_events:
                if max(start, ev_start) < min(end, ev_end):
                    overlap = True
                    break
                    
            if not overlap:
                rounding = settings["rounding_mins"]
                minutes = start.minute
                remainder = minutes % rounding
                if remainder != 0:
                    start = start + datetime.timedelta(minutes=(rounding - remainder))
                    end = start + datetime.timedelta(minutes=needed_duration)
                    if end > shift_end:
                        continue
                    overlap = False
                    for ev_start, ev_end in day_events:
                        if max(start, ev_start) < min(end, ev_end):
                            overlap = True
                            break
                    if overlap:
                        continue
                        
                valid_slots.append(start.strftime("%H:%M"))
                
    return sorted(list(set(valid_slots)))

# --- RUTAS DE LA APP WEB ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    return jsonify({
        "brand_name": brand_name,
        "services": services,
        "extras": extras,
        "appointments": appointments,
        "clients": list(clients.values()),
        "settings": settings,
        "custom_daily_hours": custom_daily_hours
    })

@app.route('/api/slots', methods=['POST'])
def api_slots():
    data = request.json
    date_str = data.get("date")
    duration = int(data.get("duration", 60))
    slots = calculate_slots(date_str, duration)
    return jsonify({"slots": slots})

@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.json
    phone = data.get("phone")
    name = data.get("name")
    surname = data.get("surname")
    service_id = int(data.get("service_id"))
    selected_extra_ids = [int(eid) for eid in data.get("extra_ids", [])]
    date_str = data.get("date")
    start_time = data.get("time")
    
    service = next(s for s in services if s["id"] == service_id)
    selected_extras = [e for e in extras if e["id"] in selected_extra_ids]
    
    total_duration = service["duration"] + sum(e["duration"] for e in selected_extras)
    total_price = service["price"] + sum(e["price"] for e in selected_extras)
    
    start_dt = datetime.datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + datetime.timedelta(minutes=total_duration)
    end_time = end_dt.strftime("%H:%M")
    
    if phone not in clients:
        clients[phone] = {"name": name, "surname": surname, "phone": phone, "email": "", "fianza_obligatoria": False, "notes": ""}
        
    new_appt = {
        "id": len(appointments) + 1,
        "client_name": f"{name} {surname}",
        "client_phone": phone,
        "service_name": service["name"],
        "extras_names": [e["name"] for e in selected_extras],
        "start_time": start_time,
        "end_time": end_time,
        "date": date_str,
        "total_price": total_price,
        "status": "Pendiente"
    }
    appointments.append(new_appt)
    return jsonify({"success": True, "appointment": new_appt})

@app.route('/api/admin/action', methods=['POST'])
def api_admin_action():
    data = request.json
    appt_id = int(data.get("id"))
    new_status = data.get("status")
    for appt in appointments:
        if appt["id"] == appt_id:
            appt["status"] = new_status
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Cita no encontrada"})

@app.route('/api/admin/hours', methods=['POST'])
def api_admin_hours():
    data = request.json
    date_str = data.get("date")
    s1, e1 = data.get("s1"), data.get("e1")
    s2, e2 = data.get("s2"), data.get("e2")
    custom_daily_hours[date_str] = [(s1, e1), (s2, e2)]
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)