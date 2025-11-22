import json
import random
from datetime import datetime, timedelta
import pytz

# Bangladesh timezone
BD_TZ = pytz.timezone('Asia/Dhaka')

# Load configuration files
with open('room_config.json', 'r') as f:
    ROOM_CONFIG = json.load(f)

with open('schedules.json', 'r') as f:
    SCHEDULES = json.load(f)

# Power fluctuation constants (Bangladesh standard)
BASE_VOLTAGE = 220  # 220V standard
VOLTAGE_VARIATION = 5  # ±5V
AC_FLUCTUATION = 0.15  # ±15% for AC
FAN_FLUCTUATION = 0.08  # ±8% for fans
LIGHT_FLUCTUATION = 0.05  # ±5% for lights
DEVICE_FLUCTUATION = 0.10  # ±10% for PC/Projector
RANDOM_NOISE = 20  # ±20W random noise

# Randomly select 5-6 rooms to be offline (changes periodically)
OFFLINE_ROOMS = []
LAST_OFFLINE_UPDATE = None


def update_offline_rooms():
    """
    Randomly select 5-6 rooms to be offline.
    Updates every 10 minutes to simulate realistic building usage.
    """
    global OFFLINE_ROOMS, LAST_OFFLINE_UPDATE
    
    current_time = datetime.now(BD_TZ)
    
    # Update offline rooms every 10 minutes
    if LAST_OFFLINE_UPDATE is None or (current_time - LAST_OFFLINE_UPDATE).total_seconds() > 600:
        all_room_ids = list(ROOM_CONFIG.keys())
        num_offline = random.randint(5, 6)
        OFFLINE_ROOMS = random.sample(all_room_ids, num_offline)
        LAST_OFFLINE_UPDATE = current_time
        print(f"🔄 Updated offline rooms: {OFFLINE_ROOMS}")


def is_room_active(room_id):
    """
    Check if a room is currently active (occupied by class).
    Returns True if class is active, False if room is offline.
    
    Logic: 34-35 rooms are online (occupied), 5-6 rooms offline (unoccupied)
    """
    update_offline_rooms()
    
    # If room is in offline list, it's not active
    if room_id in OFFLINE_ROOMS:
        return False
    
    # All other rooms are active (class in session)
    return True


def calculate_equipment_power(equipment_type, base_wattage, count):
    """
    Calculate power consumption for equipment with realistic fluctuations.
    """
    if equipment_type == 'ac':
        fluctuation = AC_FLUCTUATION
    elif equipment_type == 'fan':
        fluctuation = FAN_FLUCTUATION
    elif equipment_type == 'light':
        fluctuation = LIGHT_FLUCTUATION
    else:  # pc, projector
        fluctuation = DEVICE_FLUCTUATION
    
    # Calculate with fluctuation
    power = base_wattage * count
    variation = power * fluctuation * random.uniform(-1, 1)
    
    return power + variation


def calculate_room_power(room_id, is_active):
    """
    Calculate total power consumption for a room with realistic fluctuations.
    """
    config = ROOM_CONFIG[room_id]
    equipment = config['equipment']
    wattage = config['wattage']
    
    if not is_active:
        # Offline room - only standby power for PC and minimal lighting
        standby_power = wattage['pc'] * equipment['pc'] * 0.05  # 5% standby
        standby_power += wattage['light'] * 1 * 0.3  # One light at 30%
        noise = random.uniform(-RANDOM_NOISE, RANDOM_NOISE)
        return max(10, standby_power + noise)  # Minimum 10W
    
    # Active room - ALL equipment running at FULL POWER with fluctuations
    total_power = 0
    
    # AC - Full power (most significant load)
    total_power += calculate_equipment_power('ac', wattage['ac'], equipment['ac'])
    
    # Fans - All running
    total_power += calculate_equipment_power('fan', wattage['fan'], equipment['fan'])
    
    # Lights - All on
    total_power += calculate_equipment_power('light', wattage['light'], equipment['light'])
    
    # Projector - On during class
    total_power += calculate_equipment_power('projector', wattage['projector'], equipment['projector'])
    
    # PC - On
    total_power += calculate_equipment_power('pc', wattage['pc'], equipment['pc'])
    
    # Add random noise for realism
    noise = random.uniform(-RANDOM_NOISE, RANDOM_NOISE)
    total_power += noise
    
    return max(100, total_power)  # Minimum 100W for active room


def get_room_data(room_id, current_time=None):
    """
    Get current power data for a specific room.
    """
    is_active = is_room_active(room_id)
    
    # Calculate power
    power = calculate_room_power(room_id, is_active)
    
    # Calculate voltage with variation
    voltage = BASE_VOLTAGE + random.uniform(-VOLTAGE_VARIATION, VOLTAGE_VARIATION)
    
    # Calculate current (I = P / V)
    current = power / voltage
    
    # Get schedule info
    schedule = SCHEDULES.get(room_id)
    course_code = schedule.get('course_code') if schedule else None
    course_name = schedule.get('course_name') if schedule else None
    
    return {
        'room_id': room_id,
        'power': round(power, 2),
        'current': round(current, 2),
        'voltage': round(voltage, 2),
        'is_active': is_active,
        'status': 'ONLINE' if is_active else 'OFFLINE',
        'course_code': course_code,
        'course_name': course_name,
        'timestamp': (current_time or datetime.now(BD_TZ)).isoformat()
    }


def get_building_summary(current_time=None):
    """
    Get summary data for all 40 rooms in the building.
    """
    rooms = []
    total_power = 0
    active_count = 0
    
    for room_id in ROOM_CONFIG.keys():
        room_data = get_room_data(room_id, current_time)
        rooms.append(room_data)
        total_power += room_data['power']
        if room_data['is_active']:
            active_count += 1
    
    return {
        'rooms': rooms,
        'total_power': round(total_power, 2),
        'active_rooms': active_count,
        'total_rooms': len(ROOM_CONFIG),
        'timestamp': (current_time or datetime.now(BD_TZ)).isoformat()
    }


def generate_historical_data(room_id, hours=24):
    """
    Generate historical power data for a room over the specified hours.
    Used for charts on room detail page.
    """
    current_time = datetime.now(BD_TZ)
    historical_data = []
    
    # Generate data points (every 5 minutes for smoother charts)
    interval_minutes = 5
    total_points = (hours * 60) // interval_minutes
    
    for i in range(total_points):
        time_point = current_time - timedelta(minutes=interval_minutes * (total_points - i))
        
        # Randomly decide if room was active at that time (85% chance)
        is_active = random.random() < 0.85
        
        # Calculate power
        power = calculate_room_power(room_id, is_active)
        voltage = BASE_VOLTAGE + random.uniform(-VOLTAGE_VARIATION, VOLTAGE_VARIATION)
        current = power / voltage
        
        historical_data.append({
            'timestamp': time_point.strftime('%Y-%m-%d %H:%M:%S'),
            'power': round(power, 2),
            'current': round(current, 2),
            'voltage': round(voltage, 2),
            'is_active': is_active
        })
    
    return historical_data


def get_room_config(room_id):
    """
    Get equipment configuration for a specific room.
    """
    return ROOM_CONFIG.get(room_id)


def get_room_schedule(room_id):
    """
    Get weekly schedule for a specific room.
    """
    return SCHEDULES.get(room_id)


def calculate_daily_energy(room_id):
    """
    Calculate daily energy consumption (kWh) for a room.
    Estimates based on typical class schedule (8 hours active per day).
    """
    config = ROOM_CONFIG[room_id]
    equipment = config['equipment']
    wattage = config['wattage']
    
    # Calculate average power when active (ALL equipment at full power)
    active_power = 0
    active_power += wattage['ac'] * equipment['ac']
    active_power += wattage['fan'] * equipment['fan']
    active_power += wattage['light'] * equipment['light']
    active_power += wattage['projector'] * equipment['projector']
    active_power += wattage['pc'] * equipment['pc']
    
    # Estimate 8 hours active, 16 hours standby per day
    active_hours = 8
    standby_hours = 16
    standby_power = active_power * 0.05
    
    daily_kwh = (active_power * active_hours + standby_power * standby_hours) / 1000
    
    return round(daily_kwh, 2)


def calculate_daily_cost(room_id):
    """
    Calculate daily electricity cost in BDT.
    Bangladesh rate: 8.5 BDT/kWh
    """
    kwh = calculate_daily_energy(room_id)
    cost = kwh * 8.5
    return round(cost, 2)


def calculate_co2_saved(kwh):
    """
    Calculate CO2 emissions saved (kg) based on energy efficiency.
    Bangladesh factor: 0.71 kg CO2/kWh
    """
    co2 = kwh * 0.71
    return round(co2, 2)


if __name__ == '__main__':
    # Test the simulation
    print("=" * 60)
    print("FUB BEMS - Power Simulation Test")
    print("=" * 60)
    
    # Test building summary
    summary = get_building_summary()
    print(f"\nTotal Rooms: {summary['total_rooms']}")
    print(f"Active Rooms: {summary['active_rooms']}")
    print(f"Total Power: {summary['total_power']}W")
    print(f"Timestamp: {summary['timestamp']}")
    
    # Test individual room
    test_room = '101'
    room_data = get_room_data(test_room)
    print(f"\n--- Room {test_room} ---")
    print(f"Status: {room_data['status']}")
    print(f"Power: {room_data['power']}W")
    print(f"Current: {room_data['current']}A")
    print(f"Voltage: {room_data['voltage']}V")
    print(f"Course: {room_data['course_name']}")
    
    # Test historical data
    print(f"\n--- Historical Data (last 24 hours) ---")
    history = generate_historical_data(test_room, hours=24)
    print(f"Data points: {len(history)}")
    print(f"First: {history[0]['timestamp']} - {history[0]['power']}W")
    print(f"Last: {history[-1]['timestamp']} - {history[-1]['power']}W")
    
    print("\n" + "=" * 60)
    print("Simulation test completed successfully!")
    print("=" * 60)