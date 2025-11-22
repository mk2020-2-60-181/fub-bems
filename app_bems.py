from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import sqlite3
import json
import pytz
import simulate_data

app = Flask(__name__)

# Global monitoring flag
MONITORING_ENABLED = True

# Individual room monitoring status (all rooms ON by default)
ROOM_MONITORING = {}

# Bangladesh timezone
BD_TZ = pytz.timezone('Asia/Dhaka')

# Database setup
def init_database():
    """Initialize SQLite database."""
    conn = sqlite3.connect('energy_bems.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS energy_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            power REAL,
            current REAL,
            voltage REAL,
            kwh REAL,
            is_scheduled INTEGER,
            course TEXT,
            status TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def init_room_monitoring():
    """Initialize room monitoring status - all rooms ON by default."""
    global ROOM_MONITORING
    for room_id in simulate_data.ROOM_CONFIG.keys():
        ROOM_MONITORING[room_id] = True  # True = monitoring ON
    print(f"✓ Initialized monitoring for {len(ROOM_MONITORING)} rooms (all ON)")


def record_building_data():
    """
    Background task to record data every 60 seconds.
    """
    global MONITORING_ENABLED
    
    if not MONITORING_ENABLED:
        return
    
    try:
        conn = sqlite3.connect('energy_bems.db')
        cursor = conn.cursor()
        
        current_time = datetime.now(BD_TZ)
        building_summary = simulate_data.get_building_summary(current_time)
        
        total_power = 0
        
        for room in building_summary['rooms']:
            # Only record if room monitoring is enabled
            if ROOM_MONITORING.get(room['room_id'], True):
                # Calculate energy (kWh) - assume 1 hour interval
                kwh = room['power'] / 1000.0
                
                cursor.execute('''
                    INSERT INTO energy_readings 
                    (room_id, timestamp, power, current, voltage, kwh, is_scheduled, course, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    room['room_id'],
                    current_time.isoformat(),
                    room['power'],
                    room['current'],
                    room['voltage'],
                    kwh,
                    1 if room['is_active'] else 0,
                    room['course_name'],
                    room['status']
                ))
                
                total_power += room['power']
        
        conn.commit()
        conn.close()
        
        timestamp_str = current_time.strftime('%H:%M:%S')
        monitored_count = sum(1 for v in ROOM_MONITORING.values() if v)
        print(f"✓ [{timestamp_str}] Recorded {monitored_count} rooms | Building: {int(total_power)}W")
        
    except Exception as e:
        print(f"✗ Error recording data: {e}")


# Initialize database and room monitoring
init_database()
init_room_monitoring()

# Setup background scheduler
scheduler = BackgroundScheduler(timezone=BD_TZ)
scheduler.add_job(func=record_building_data, trigger="interval", seconds=60)
scheduler.start()


# ============= ROUTES =============

@app.route('/')
def dashboard():
    """Main dashboard page."""
    return render_template('building_dashboard.html')


@app.route('/room/<room_id>')
def room_detail(room_id):
    """Room detail page."""
    return render_template('room_detail.html', room_id=room_id)


# ============= API ENDPOINTS =============

@app.route('/api/building/status')
def get_building_status():
    """
    Get current status of all 40 rooms.
    """
    try:
        summary = simulate_data.get_building_summary()
        
        # Add room monitoring status to each room
        for room in summary['rooms']:
            room['monitoring_enabled'] = ROOM_MONITORING.get(room['room_id'], True)
        
        # Calculate ONLY rooms with monitoring enabled
        # Count rooms that are both active AND have monitoring enabled
        monitored_active_rooms = sum(
            1 for room in summary['rooms'] 
            if room['is_active'] and ROOM_MONITORING.get(room['room_id'], True)
        )
        
        # Total rooms with monitoring enabled (regardless of active status)
        total_monitored_rooms = sum(1 for v in ROOM_MONITORING.values() if v)
        
        # Calculate daily energy and cost for the building
        total_daily_kwh = 0
        for room_id in simulate_data.ROOM_CONFIG.keys():
            # Only count energy for monitored rooms
            if ROOM_MONITORING.get(room_id, True):
                total_daily_kwh += simulate_data.calculate_daily_energy(room_id)
        
        total_daily_cost = total_daily_kwh * 8.5
        co2_saved = simulate_data.calculate_co2_saved(total_daily_kwh)
        
        return jsonify({
            'success': True,
            'timestamp': summary['timestamp'],
            'monitoring_enabled': MONITORING_ENABLED,
            'total_power': summary['total_power'],
            'active_rooms': monitored_active_rooms,  # Only monitored active rooms
            'total_rooms': total_monitored_rooms,     # Total rooms with monitoring ON
            'total_rooms_building': 40,               # Always 40 physical rooms
            'daily_energy': round(total_daily_kwh, 2),
            'daily_cost': round(total_daily_cost, 2),
            'co2_saved': co2_saved,
            'rooms': summary['rooms']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/room/<room_id>/status')
def get_room_status(room_id):
    """
    Get current status for a specific room.
    """
    try:
        if room_id not in simulate_data.ROOM_CONFIG:
            return jsonify({'success': False, 'error': 'Room not found'}), 404
        
        room_data = simulate_data.get_room_data(room_id)
        daily_kwh = simulate_data.calculate_daily_energy(room_id)
        daily_cost = simulate_data.calculate_daily_cost(room_id)
        
        return jsonify({
            'success': True,
            'room_id': room_id,
            'power': room_data['power'],
            'current': room_data['current'],
            'voltage': room_data['voltage'],
            'status': room_data['status'],
            'is_active': room_data['is_active'],
            'course_code': room_data['course_code'],
            'course_name': room_data['course_name'],
            'daily_energy': daily_kwh,
            'daily_cost': daily_cost,
            'monitoring_enabled': ROOM_MONITORING.get(room_id, True),
            'timestamp': room_data['timestamp']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/room/<room_id>/history')
def get_room_history(room_id):
    """
    Get 24-hour historical data for a room.
    """
    try:
        if room_id not in simulate_data.ROOM_CONFIG:
            return jsonify({'success': False, 'error': 'Room not found'}), 404
        
        hours = request.args.get('hours', default=24, type=int)
        historical_data = simulate_data.generate_historical_data(room_id, hours)
        
        return jsonify({
            'success': True,
            'room_id': room_id,
            'data_points': len(historical_data),
            'data': historical_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/room/<room_id>/schedule')
def get_room_schedule(room_id):
    """
    Get weekly schedule for a room.
    """
    try:
        if room_id not in simulate_data.ROOM_CONFIG:
            return jsonify({'success': False, 'error': 'Room not found'}), 404
        
        schedule = simulate_data.get_room_schedule(room_id)
        
        return jsonify({
            'success': True,
            'room_id': room_id,
            'course_code': schedule.get('course_code'),
            'course_name': schedule.get('course_name'),
            'schedule': schedule.get('schedule', [])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/room/<room_id>/config')
def get_room_config(room_id):
    """
    Get equipment configuration for a room.
    """
    try:
        if room_id not in simulate_data.ROOM_CONFIG:
            return jsonify({'success': False, 'error': 'Room not found'}), 404
        
        config = simulate_data.get_room_config(room_id)
        
        return jsonify({
            'success': True,
            'room_id': room_id,
            'floor': config['floor'],
            'capacity': config['capacity'],
            'equipment': config['equipment'],
            'wattage': config['wattage']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monitoring/toggle', methods=['POST'])
def toggle_monitoring():
    """
    Pause or resume global monitoring.
    """
    global MONITORING_ENABLED
    
    try:
        MONITORING_ENABLED = not MONITORING_ENABLED
        
        status = "RESUMED" if MONITORING_ENABLED else "PAUSED"
        icon = "▶" if MONITORING_ENABLED else "⏸"
        
        print(f"{icon} Global monitoring {status}")
        
        return jsonify({
            'success': True,
            'monitoring_enabled': MONITORING_ENABLED,
            'message': f'Global monitoring {status}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/room/<room_id>/monitoring/toggle', methods=['POST'])
def toggle_room_monitoring(room_id):
    """
    Toggle monitoring for a specific room.
    """
    global ROOM_MONITORING
    
    try:
        if room_id not in simulate_data.ROOM_CONFIG:
            return jsonify({'success': False, 'error': 'Room not found'}), 404
        
        # Toggle the room's monitoring status
        current_status = ROOM_MONITORING.get(room_id, True)
        ROOM_MONITORING[room_id] = not current_status
        
        new_status = ROOM_MONITORING[room_id]
        status_text = "ON" if new_status else "OFF"
        icon = "✓" if new_status else "✗"
        
        # Count how many rooms are currently being monitored
        monitored_count = sum(1 for v in ROOM_MONITORING.values() if v)
        
        print(f"{icon} Room {room_id} monitoring: {status_text} | Total monitored: {monitored_count}/40")
        
        return jsonify({
            'success': True,
            'room_id': room_id,
            'monitoring_enabled': new_status,
            'total_monitored': monitored_count,
            'message': f'Room {room_id} monitoring {status_text}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ============= STARTUP =============

if __name__ == '__main__':
    print("=" * 60)
    print("🏢 FUB Building Energy Management System (BEMS)")
    print("=" * 60)
    print(f"📊 Monitoring: 40 classrooms")
    print(f"📅 Schedules loaded for: 35 active classes")
    print(f"🔄 Background data collection: Every 60 seconds")
    print(f"🎛️  Individual room control: ON/OFF switches available")
    print(f"🌐 Dashboard: http://127.0.0.1:5000")
    print(f"⏸  Pause/Resume: Use buttons in dashboard")
    print("=" * 60)
    
    # Record initial data
    record_building_data()
    
    # Run Flask app
    app.run(debug=True, use_reloader=False)
