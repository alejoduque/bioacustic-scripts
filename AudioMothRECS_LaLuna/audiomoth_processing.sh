#!/bin/bash
# Script para procesar múltiples archivos AudioMoth y generar tabla HTML con enlaces directos

VENV_DIR="$HOME/.audiomoth_venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detectar el comando Python correcto
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Error: Python no está instalado"
    echo "En Mac con Homebrew, instala con: brew install python3"
    exit 1
fi

echo "✓ Usando: $PYTHON_CMD"

# Verificar si el entorno virtual existe
if [ ! -d "$VENV_DIR" ]; then
    echo "Creando entorno virtual por primera vez..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    
    echo "Instalando metamoth..."
    "$VENV_DIR/bin/pip" install --quiet metamoth
    
    echo "¡Configuración completada!"
    echo ""
fi

# Activar el entorno virtual y ejecutar el script Python
"$VENV_DIR/bin/python" - "$@" << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""
Procesador batch de archivos WAV de AudioMoth con enlaces directos y visualizador
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from metamoth import parse_metadata


# Diccionario OPCIONAL para mapear AudioMoth ID a coordenadas y fechas
DEPLOYMENT_INFO = {
    # Ejemplo:
    # "24E1440163ED0711": {
    #     "latitud": 4.7110,
    #     "longitud": -74.0721,
    #     "fecha_instalacion": "2024-07-27"
    # }
}

# Diccionario para mapear nombres de carpetas a coordenadas (OPCIONAL)
LOCATION_COORDS = {
    # Ejemplo:
    # "Bosque de galería y-o ripario": {"latitud": 4.7110, "longitud": -74.0721},
}


def get_quality_label(samplerate_hz, gain):
    """Determina la calidad de grabación basada en sample rate y ganancia"""
    gain_str = str(gain).split('.')[-1] if hasattr(gain, 'name') else str(gain)
    
    if samplerate_hz >= 384000:
        quality = "Ultra Alta"
    elif samplerate_hz >= 192000:
        quality = "Muy Alta"
    elif samplerate_hz >= 96000:
        quality = "Alta"
    elif samplerate_hz >= 48000:
        quality = "Media"
    else:
        quality = "Estándar"
    
    return f"{quality} ({samplerate_hz/1000:.0f} kHz, {gain_str})"


def extract_location_from_path(filepath):
    """Extrae información de ubicación de la estructura de carpetas"""
    path = Path(filepath)
    path_parts = path.parts
    
    location_info = {
        "sitio": None,
        "epoca": None,
        "cobertura": None
    }
    
    parent_dir = path.parent.name
    
    known_coverages = [
        "Bosque de galería y-o ripario",
        "Bosque denso alto de tierra firme",
        "Cultivos permanentes arbóreos",
        "Lagunas, lagos y ciénagas naturales",
        "Mosaico de cultivos",
        "Otros cultivos transitorios",
        "Palmas de aceite",
        "Pastos arbolados",
        "Pastos enmalezados",
        "Pastos limpios",
        "Plantación de latifoliadas",
        "Tierras desnudas y degradadas",
        "Vegetación secundaria alta",
        "Vegetación secundaria baja",
        "Zonas pantanosas"
    ]
    
    for part in path_parts:
        if "LunaCaptiva" in part or "Luna" in part or "Captiva" in part:
            location_info["sitio"] = "Luna Captiva"
        
        if "lluvia" in part.lower():
            location_info["epoca"] = "Época lluvias"
        elif "seca" in part.lower() or "seco" in part.lower():
            location_info["epoca"] = "Época seca"
        
        for coverage in known_coverages:
            if part == coverage:
                location_info["cobertura"] = coverage
                break
    
    if not location_info["cobertura"]:
        location_info["cobertura"] = parent_dir
    
    return location_info


def create_file_url(filepath, use_relative=True):
    """Crea una URL para acceder al archivo"""
    abs_path = os.path.abspath(filepath)
    
    if use_relative:
        # Intenta crear una ruta relativa desde el directorio actual
        try:
            rel_path = os.path.relpath(filepath)
            return quote(rel_path)
        except ValueError:
            # Si falla, usa la ruta absoluta
            pass
    
    # Convierte a URL file://
    if sys.platform.startswith('win'):
        # Windows
        file_url = 'file:///' + abs_path.replace('\\', '/')
    else:
        # Unix/Linux/Mac
        file_url = 'file://' + abs_path
    
    return quote(file_url, safe=':/')


def process_wav_file(filepath):
    """Procesa un archivo WAV y extrae sus metadatos"""
    try:
        metadata = parse_metadata(filepath)
        
        location_info = extract_location_from_path(filepath)
        
        ubicacion_parts = []
        if location_info["cobertura"]:
            ubicacion_parts.append(location_info["cobertura"])
        if location_info["epoca"]:
            ubicacion_parts.append(f"({location_info['epoca']})")
        if location_info["sitio"]:
            ubicacion_parts.append(f"- {location_info['sitio']}")
        
        ubicacion = " ".join(ubicacion_parts) if ubicacion_parts else "Ubicación no especificada"
        
        audiomoth_id = getattr(metadata, 'audiomoth_id', 'Unknown')
        deployment = DEPLOYMENT_INFO.get(audiomoth_id, {})
        
        coords_info = LOCATION_COORDS.get(location_info["cobertura"], {})
        latitud = deployment.get('latitud') or coords_info.get('latitud')
        longitud = deployment.get('longitud') or coords_info.get('longitud')
        
        if latitud and longitud:
            coords = f"{latitud}, {longitud}"
        else:
            coords = "No disponible"
        
        fecha_instalacion = deployment.get('fecha_instalacion', 'N/A')
        dt = getattr(metadata, 'datetime', None)
        if fecha_instalacion == 'N/A' and dt:
            fecha_instalacion = dt.strftime('%Y-%m-%d')
        
        return {
            "archivo": Path(filepath).name,
            "ruta_completa": str(filepath),
            "ruta_absoluta": os.path.abspath(filepath),
            "file_url": create_file_url(filepath),
            "duracion_s": getattr(metadata, 'duration_s', 0),
            "datetime": getattr(metadata, 'datetime', None),
            "timezone": getattr(metadata, 'timezone', 'UTC'),
            "ubicacion": ubicacion,
            "cobertura": location_info["cobertura"],
            "epoca": location_info["epoca"],
            "sitio": location_info["sitio"],
            "coordenadas": coords,
            "fecha_instalacion": fecha_instalacion,
            "calidad": get_quality_label(
                getattr(metadata, 'samplerate_hz', 0),
                getattr(metadata, 'gain', 'Unknown')
            ),
            "temperatura_c": getattr(metadata, 'temperature_c', None),
            "battery_v": getattr(metadata, 'battery_state_v', None),
            "audiomoth_id": audiomoth_id,
            "error": None
        }
    except Exception as e:
        return {
            "archivo": Path(filepath).name,
            "ruta_completa": str(filepath),
            "ruta_absoluta": os.path.abspath(filepath),
            "file_url": create_file_url(filepath),
            "error": str(e)
        }


def find_wav_files(directory):
    """Encuentra todos los archivos WAV en el directorio y subdirectorios"""
    wav_files = []
    path = Path(directory)
    
    if path.is_file() and path.suffix.lower() == '.wav':
        return [str(path)]
    
    for wav_file in path.rglob('*.WAV'):
        wav_files.append(str(wav_file))
    for wav_file in path.rglob('*.wav'):
        wav_files.append(str(wav_file))
    
    return sorted(wav_files)


def prepare_for_json(obj):
    """Convierte objetos Python a tipos serializables en JSON recursivamente"""
    if obj is None:
        return None
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, (int, float, str, bool)):
        return obj
    elif isinstance(obj, dict):
        return {k: prepare_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [prepare_for_json(item) for item in obj]
    else:
        # Para cualquier otro objeto, convertir a string
        return str(obj)


def generate_html(results, output_file):
    """Genera una tabla HTML con los resultados y enlaces directos"""
    
    # Preparar datos para gráficos
    chart_data = []
    for r in results:
        if not r.get('error') and r.get('datetime') and r.get('temperatura_c'):
            dt = r['datetime']
            chart_data.append({
                'hora': dt.hour + dt.minute/60,
                'temperatura': r['temperatura_c'],
                'fecha': dt.strftime('%Y-%m-%d'),
                'archivo': r['archivo'],
                'ubicacion': r.get('cobertura', 'N/A')
            })
    
    import json
    chart_data_json = json.dumps(chart_data)
    
    html = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Metadatos AudioMoth - Visualizador Interactivo</title>
    <script src="https://cdn.plot.ly/plotly-3.3.0.min.js" charset="utf-8"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .summary {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        
        .summary-item {
            text-align: center;
        }
        
        .summary-label {
            font-weight: 600;
            color: #7f8c8d;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
        }
        
        .summary-value {
            color: #2c3e50;
            font-size: 32px;
            font-weight: bold;
        }
        
        .controls {
            background: white;
            padding: 15px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .filter-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .filter-group input,
        .filter-group select {
            padding: 8px 12px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .filter-group input:focus,
        .filter-group select:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .table-container {
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 10;
            cursor: pointer;
            user-select: none;
        }
        
        th:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
        }
        
        td {
            padding: 12px;
            border-bottom: 1px solid #f0f0f0;
        }
        
        tr:hover {
            background-color: #f8f9fa;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        .filename {
            font-family: 'Courier New', monospace;
            font-size: 13px;
            color: #34495e;
            font-weight: 600;
        }
        
        .play-btn {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: transform 0.2s, box-shadow 0.2s;
            text-decoration: none;
        }
        
        .play-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(102, 126, 234, 0.4);
        }
        
        .play-btn:active {
            transform: translateY(0);
        }
        
        .download-btn {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            margin-left: 5px;
        }
        
        .location {
            color: #16a085;
            font-weight: 500;
        }
        
        .coords {
            font-size: 11px;
            color: #7f8c8d;
            font-style: italic;
        }
        
        .quality-ultra { color: #27ae60; font-weight: bold; }
        .quality-high { color: #2ecc71; }
        .quality-medium { color: #f39c12; }
        
        .temp-cold { color: #3498db; }
        .temp-warm { color: #e67e22; }
        .temp-hot { color: #e74c3c; }
        
        .error {
            color: #e74c3c;
            font-style: italic;
        }
        
        .audio-player {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            display: none;
        }
        
        .audio-player.active {
            display: block;
        }
        
        .audio-player audio {
            width: 100%;
            margin-top: 10px;
        }
        
        .player-info {
            font-size: 14px;
            color: #2c3e50;
            margin-bottom: 5px;
        }
        
        footer {
            margin-top: 30px;
            text-align: center;
            color: white;
            font-size: 13px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }
        
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            background: #ecf0f1;
            color: #2c3e50;
        }
        
        /* Modal del reproductor */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.8);
            animation: fadeIn 0.3s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .modal.active {
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 16px;
            max-width: 800px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
            animation: slideUp 0.3s;
        }
        
        @keyframes slideUp {
            from {
                transform: translateY(50px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #e0e0e0;
        }
        
        .modal-title {
            font-size: 1.5em;
            color: #2c3e50;
            font-weight: 700;
            word-break: break-all;
        }
        
        .close-btn {
            background: #e74c3c;
            color: white;
            border: none;
            width: 35px;
            height: 35px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 20px;
            line-height: 1;
            transition: all 0.3s;
            flex-shrink: 0;
            margin-left: 15px;
        }
        
        .close-btn:hover {
            background: #c0392b;
            transform: rotate(90deg);
        }
        
        .audio-player-modal {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
        }
        
        .audio-player-modal audio {
            width: 100%;
            margin-top: 10px;
        }
        
        .audio-info {
            color: white;
            font-size: 14px;
            margin-bottom: 10px;
        }
        
        .metadata-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .metadata-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .metadata-label {
            font-size: 11px;
            text-transform: uppercase;
            color: #7f8c8d;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        
        .metadata-value {
            font-size: 16px;
            color: #2c3e50;
            font-weight: 600;
        }
        
        .metadata-icon {
            margin-right: 5px;
        }
        
        .action-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 20px;
        }
        
        .action-btn {
            flex: 1;
            min-width: 150px;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .action-btn.primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .action-btn.secondary {
            background: #ecf0f1;
            color: #2c3e50;
        }
        
        .action-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        .waveform-placeholder {
            background: linear-gradient(to right, #e0e0e0 0%, #f5f5f5 50%, #e0e0e0 100%);
            height: 80px;
            border-radius: 8px;
            margin: 15px 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #7f8c8d;
            font-style: italic;
        }
        
        .instructions {
            background: #fff3cd;
            border: 2px solid #ffc107;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .instructions h3 {
            color: #856404;
            margin-bottom: 10px;
        }
        
        .instructions p {
            color: #856404;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .instructions code {
            background: #ffeaa7;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
        
        .charts-section {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .charts-section h2 {
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.5em;
        }
        
        .chart-container {
            margin-bottom: 20px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 10px;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .tab-btn {
            padding: 10px 20px;
            border: none;
            background: #ecf0f1;
            color: #2c3e50;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .tab-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .tab-btn:hover {
            transform: translateY(-2px);
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Visualizador AudioMoth Interactivo</h1>
        
        <div class="instructions">
            <h3>📌 Cómo escuchar los archivos:</h3>
            <p>
                <strong>🎵 Haz clic en "▶️ Reproducir"</strong> para abrir el reproductor integrado con toda la información del archivo.<br>
                <strong>Opción alternativa:</strong> Usa "🔗 Abrir ubicación" para navegar al archivo en tu sistema.
            </p>
        </div>
        
        <!-- Modal del reproductor -->
        <div id="audioModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title" id="modalTitle">Archivo de audio</h2>
                    <button class="close-btn" onclick="closeModal()">&times;</button>
                </div>
                
                <div class="audio-player-modal">
                    <div class="audio-info" id="audioInfo">Cargando...</div>
                    <audio id="modalAudioPlayer" controls preload="metadata"></audio>
                </div>
                
                <div class="metadata-grid" id="metadataGrid">
                    <!-- Se llenará dinámicamente con JavaScript -->
                </div>
                
                <div class="action-buttons">
                    <button class="action-btn secondary" onclick="copyToClipboard()">
                        📋 Copiar ruta
                    </button>
                    <button class="action-btn secondary" onclick="openInFolder()">
                        📁 Abrir carpeta
                    </button>
                    <button class="action-btn primary" onclick="closeModal()">
                        ✓ Cerrar
                    </button>
                </div>
            </div>
        </div>
        
        <div class="summary">
"""
    
    # Calcular estadísticas
    total_files = len(results)
    total_errors = sum(1 for r in results if r.get('error'))
    total_duration = sum(r.get('duracion_s', 0) for r in results if not r.get('error'))
    unique_locations = len(set(r.get('ubicacion', '') for r in results if not r.get('error')))
    
    html += f"""
            <div class="summary-item">
                <div class="summary-label">Total Archivos</div>
                <div class="summary-value">{total_files}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Duración Total</div>
                <div class="summary-value">{total_duration/3600:.1f}h</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Ubicaciones</div>
                <div class="summary-value">{unique_locations}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Errores</div>
                <div class="summary-value">{total_errors}</div>
            </div>
        </div>
        
        <div class="charts-section">
            <h2>📊 Análisis de Datos</h2>
            
            <div class="tabs">
                <button class="tab-btn active" onclick="showTab('temp-time')">🌡️ Temperatura vs Hora</button>
                <button class="tab-btn" onclick="showTab('temp-location')">📍 Temperatura por Ubicación</button>
                <button class="tab-btn" onclick="showTab('recordings-time')">⏰ Grabaciones por Hora</button>
            </div>
            
            <div id="temp-time" class="tab-content active">
                <div class="chart-container">
                    <div id="tempTimeChart" style="width:100%; height:500px;"></div>
                </div>
            </div>
            
            <div id="temp-location" class="tab-content">
                <div class="chart-container">
                    <div id="tempLocationChart" style="width:100%; height:500px;"></div>
                </div>
            </div>
            
            <div id="recordings-time" class="tab-content">
                <div class="chart-container">
                    <div id="recordingsTimeChart" style="width:100%; height:500px;"></div>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <div class="filter-group">
                <input type="text" id="searchInput" placeholder="🔍 Buscar archivo..." style="flex: 1; min-width: 200px;">
                <select id="locationFilter">
                    <option value="">Todas las ubicaciones</option>
"""
    
    # Agregar opciones de ubicación
    locations = sorted(set(r.get('ubicacion', '') for r in results if not r.get('error') and r.get('ubicacion')))
    for loc in locations:
        html += f'                    <option value="{loc}">{loc}</option>\n'
    
    html += """
                </select>
                <button onclick="resetFilters()" style="padding: 8px 15px; background: #e74c3c; color: white; border: none; border-radius: 6px; cursor: pointer;">
                    🔄 Limpiar filtros
                </button>
            </div>
        </div>
        
        <div id="audioPlayerContainer" class="audio-player">
            <div class="player-info" id="playerInfo"></div>
            <audio id="audioPlayer" controls></audio>
        </div>
        
        <div class="table-container">
            <table id="dataTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Acciones</th>
                        <th onclick="sortTable(1)">Archivo</th>
                        <th onclick="sortTable(2)">Fecha y Hora</th>
                        <th onclick="sortTable(3)">Duración</th>
                        <th onclick="sortTable(4)">Ubicación</th>
                        <th onclick="sortTable(5)">Instalación</th>
                        <th onclick="sortTable(6)">Calidad</th>
                        <th onclick="sortTable(7)">Temp.</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for result in results:
        if result.get('error'):
            html += f"""
                    <tr>
                        <td></td>
                        <td class="filename">{result['archivo']}</td>
                        <td colspan="6" class="error">⚠️ Error: {result['error']}</td>
                    </tr>
"""
        else:
            dt = result['datetime']
            if dt:
                fecha_hora = dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                fecha_hora = "N/A"
            
            duracion_min = result['duracion_s'] / 60
            if duracion_min >= 60:
                duracion_display = f"{duracion_min/60:.1f}h"
            else:
                duracion_display = f"{duracion_min:.1f}m"
            
            temp = result['temperatura_c']
            if temp:
                if temp < 20:
                    temp_class = "temp-cold"
                elif temp < 30:
                    temp_class = "temp-warm"
                else:
                    temp_class = "temp-hot"
                temp_display = f'<span class="{temp_class}">{temp}°C</span>'
            else:
                temp_display = "N/A"
            
            if "Ultra" in result['calidad']:
                quality_class = "quality-ultra"
            elif "Alta" in result['calidad']:
                quality_class = "quality-high"
            else:
                quality_class = "quality-medium"
            
            # Crear enlaces
            file_path = result['ruta_absoluta'].replace('\\', '/')
            folder_path = str(Path(result['ruta_absoluta']).parent).replace('\\', '/')
            
            # Preparar datos para JSON (convertir objetos no serializables recursivamente)
            result_json = prepare_for_json(result)
            result_json_str = json.dumps(result_json, ensure_ascii=False)
            
            html += f"""
                    <tr data-location="{result['ubicacion']}" data-filename="{result['archivo'].lower()}">
                        <td>
                            <button onclick='playAudio({result_json_str})' class="play-btn" title="Reproducir en el navegador">
                                ▶️ Reproducir
                            </button>
                            <a href="{result['file_url']}" class="play-btn download-btn" target="_blank" title="Abrir ubicación del archivo">
                                🔗 Ubicación
                            </a>
                        </td>
                        <td class="filename" title="{result['ruta_completa']}">{result['archivo']}</td>
                        <td>{fecha_hora}<br><small class="badge">{result['timezone']}</small></td>
                        <td>{duracion_display}</td>
                        <td class="location">
                            {result['ubicacion']}<br>
                            <span class="coords">📍 {result['coordenadas']}</span>
                        </td>
                        <td>{result['fecha_instalacion']}</td>
                        <td class="{quality_class}">{result['calidad']}</td>
                        <td>{temp_display}</td>
                    </tr>
"""
    
    html += """
                </tbody>
            </table>
        </div>
        
        <footer>
            Generado el """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """ | 
            Total de """ + str(total_files) + """ archivos | 
            Duración acumulada: """ + f"{total_duration/3600:.2f}" + """ horas
        </footer>
    </div>
    
    <script>
        // Variable global para almacenar el archivo actual
        let currentFile = null;
        
        // Datos para gráficos
        const chartData = """ + chart_data_json + """;
        
        console.log('Chart data loaded:', chartData.length, 'registros');
        
        // Verificar que Plotly esté disponible
        if (typeof Plotly === 'undefined') {
            console.error('Plotly no se cargó correctamente');
            document.querySelector('.charts-section').innerHTML = 
                '<div style="padding:20px;background:#ffebee;border-radius:8px;color:#c62828;">' +
                '<h3>⚠️ Error: No se pudo cargar la librería de gráficos</h3>' +
                '<p>Por favor, verifica tu conexión a internet.</p></div>';
        }
        
        // Gráfico 1: Temperatura vs Hora del día
        function createTempTimeChart() {
            const locations = [...new Set(chartData.map(d => d.ubicacion))];
            const traces = locations.map(location => {
                const filtered = chartData.filter(d => d.ubicacion === location);
                return {
                    x: filtered.map(d => d.hora),
                    y: filtered.map(d => d.temperatura),
                    mode: 'markers',
                    type: 'scatter',
                    name: location,
                    text: filtered.map(d => `${d.archivo}<br>Fecha: ${d.fecha}<br>Hora: ${Math.floor(d.hora)}:${Math.round((d.hora % 1) * 60).toString().padStart(2, '0')}<br>Temp: ${d.temperatura}°C`),
                    hovertemplate: '%{text}<extra></extra>',
                    marker: {
                        size: 8,
                        opacity: 0.7
                    }
                };
            });
            
            const layout = {
                title: 'Temperatura vs Hora del Día',
                xaxis: {
                    title: 'Hora del día',
                    tickmode: 'linear',
                    tick0: 0,
                    dtick: 2,
                    tickformat: '%H:00',
                    range: [0, 24]
                },
                yaxis: {
                    title: 'Temperatura (°C)'
                },
                hovermode: 'closest',
                showlegend: true,
                legend: {
                    orientation: 'v',
                    x: 1.02,
                    y: 1
                }
            };
            
            Plotly.newPlot('tempTimeChart', traces, layout, {responsive: true});
        }
        
        // Gráfico 2: Temperatura por ubicación (boxplot)
        function createTempLocationChart() {
            const locations = [...new Set(chartData.map(d => d.ubicacion))];
            const traces = locations.map(location => {
                const temps = chartData.filter(d => d.ubicacion === location).map(d => d.temperatura);
                return {
                    y: temps,
                    type: 'box',
                    name: location,
                    boxmean: 'sd'
                };
            });
            
            const layout = {
                title: 'Distribución de Temperatura por Ubicación',
                yaxis: {
                    title: 'Temperatura (°C)'
                },
                showlegend: false
            };
            
            Plotly.newPlot('tempLocationChart', traces, layout, {responsive: true});
        }
        
        // Gráfico 3: Cantidad de grabaciones por hora
        function createRecordingsTimeChart() {
            const hourCounts = {};
            chartData.forEach(d => {
                const hour = Math.floor(d.hora);
                hourCounts[hour] = (hourCounts[hour] || 0) + 1;
            });
            
            const hours = Array.from({length: 24}, (_, i) => i);
            const counts = hours.map(h => hourCounts[h] || 0);
            
            const trace = {
                x: hours,
                y: counts,
                type: 'bar',
                marker: {
                    color: counts,
                    colorscale: 'Viridis'
                },
                text: counts.map(c => c > 0 ? c : ''),
                textposition: 'outside'
            };
            
            const layout = {
                title: 'Cantidad de Grabaciones por Hora del Día',
                xaxis: {
                    title: 'Hora del día',
                    tickmode: 'linear',
                    tick0: 0,
                    dtick: 1
                },
                yaxis: {
                    title: 'Cantidad de grabaciones'
                }
            };
            
            Plotly.newPlot('recordingsTimeChart', [trace], layout, {responsive: true});
        }
        
        // Crear gráficos al cargar
        if (chartData.length > 0) {
            console.log('Creando gráficos...');
            try {
                createTempTimeChart();
                createTempLocationChart();
                createRecordingsTimeChart();
                console.log('Gráficos creados exitosamente');
            } catch (error) {
                console.error('Error creando gráficos:', error);
                document.querySelector('.charts-section').innerHTML = 
                    '<div style="padding:20px;background:#ffebee;border-radius:8px;color:#c62828;">' +
                    '<h3>⚠️ Error al crear gráficos</h3>' +
                    '<p>' + error.message + '</p></div>';
            }
        } else {
            console.warn('No hay datos para crear gráficos');
            document.querySelector('.charts-section').innerHTML = 
                '<div style="padding:20px;background:#fff9c4;border-radius:8px;color:#f57f17;">' +
                '<h3>ℹ️ No hay datos suficientes</h3>' +
                '<p>No se encontraron registros con temperatura para generar gráficos.</p></div>';
        }
        
        // Sistema de tabs
        function showTab(tabId) {
            // Ocultar todos los tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Mostrar el tab seleccionado
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
        }
        
        // Funciones del modal del reproductor
        function playAudio(fileData) {
            currentFile = fileData;
            const modal = document.getElementById('audioModal');
            const modalTitle = document.getElementById('modalTitle');
            const audioInfo = document.getElementById('audioInfo');
            const audioPlayer = document.getElementById('modalAudioPlayer');
            const metadataGrid = document.getElementById('metadataGrid');
            
            // Actualizar título
            modalTitle.textContent = fileData.archivo;
            
            // Actualizar info del reproductor
            audioInfo.innerHTML = `
                <strong>📂 ${fileData.ubicacion}</strong><br>
                <span style="font-size: 12px; opacity: 0.9;">Haz clic en play para escuchar la grabación</span>
            `;
            
            // Configurar el reproductor de audio
            // Construir URL relativa para el servidor local
            const relativePath = fileData.ruta_completa.split('/').slice(-3).join('/');
            audioPlayer.src = relativePath;
            
            // Crear grid de metadata
            const dt = new Date(fileData.datetime);
            const metadata = [
                {
                    icon: '📅',
                    label: 'Fecha de grabación',
                    value: dt ? dt.toLocaleDateString('es-ES', { 
                        weekday: 'long', 
                        year: 'numeric', 
                        month: 'long', 
                        day: 'numeric' 
                    }) : 'N/A'
                },
                {
                    icon: '⏰',
                    label: 'Hora de grabación',
                    value: dt ? dt.toLocaleTimeString('es-ES') + ' (' + fileData.timezone + ')' : 'N/A'
                },
                {
                    icon: '⏱️',
                    label: 'Duración',
                    value: formatDuration(fileData.duracion_s)
                },
                {
                    icon: '🌡️',
                    label: 'Temperatura',
                    value: fileData.temperatura_c ? fileData.temperatura_c + '°C' : 'N/A',
                    color: getTempColor(fileData.temperatura_c)
                },
                {
                    icon: '📍',
                    label: 'Ubicación',
                    value: fileData.cobertura || 'N/A'
                },
                {
                    icon: '🌿',
                    label: 'Época',
                    value: fileData.epoca || 'N/A'
                },
                {
                    icon: '📡',
                    label: 'Calidad de grabación',
                    value: fileData.calidad
                },
                {
                    icon: '🗓️',
                    label: 'Instalación',
                    value: fileData.fecha_instalacion
                },
                {
                    icon: '🔋',
                    label: 'Batería',
                    value: fileData.battery_v ? fileData.battery_v.toFixed(2) + 'V' : 'N/A'
                },
                {
                    icon: '🎙️',
                    label: 'AudioMoth ID',
                    value: fileData.audiomoth_id
                },
                {
                    icon: '🌐',
                    label: 'Coordenadas',
                    value: fileData.coordenadas
                },
                {
                    icon: '📂',
                    label: 'Ruta',
                    value: fileData.ruta_completa,
                    small: true
                }
            ];
            
            metadataGrid.innerHTML = metadata.map(item => `
                <div class="metadata-item" ${item.color ? `style="border-left-color: ${item.color}"` : ''}>
                    <div class="metadata-label">
                        <span class="metadata-icon">${item.icon}</span>
                        ${item.label}
                    </div>
                    <div class="metadata-value" ${item.small ? 'style="font-size: 11px; word-break: break-all;"' : ''}>
                        ${item.value}
                    </div>
                </div>
            `).join('');
            
            // Mostrar modal
            modal.classList.add('active');
        }
        
        function closeModal() {
            const modal = document.getElementById('audioModal');
            const audioPlayer = document.getElementById('modalAudioPlayer');
            
            // Pausar audio
            audioPlayer.pause();
            audioPlayer.src = '';
            
            // Ocultar modal
            modal.classList.remove('active');
        }
        
        function copyToClipboard() {
            if (currentFile) {
                navigator.clipboard.writeText(currentFile.ruta_completa).then(() => {
                    alert('✓ Ruta copiada al portapapeles');
                }).catch(() => {
                    alert('⚠️ No se pudo copiar al portapapeles');
                });
            }
        }
        
        function openInFolder() {
            if (currentFile) {
                window.open(currentFile.file_url, '_blank');
            }
        }
        
        function formatDuration(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);
            
            if (hours > 0) {
                return `${hours}h ${minutes}m ${secs}s`;
            } else if (minutes > 0) {
                return `${minutes}m ${secs}s`;
            } else {
                return `${secs}s`;
            }
        }
        
        function getTempColor(temp) {
            if (!temp) return '#7f8c8d';
            if (temp < 20) return '#3498db';
            if (temp < 30) return '#e67e22';
            return '#e74c3c';
        }
        
        // Cerrar modal al hacer clic fuera de él
        document.getElementById('audioModal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal();
            }
        });
        
        // Cerrar modal con tecla ESC
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeModal();
            }
        });
        
        // Filtrado de tabla
        const searchInput = document.getElementById('searchInput');
        const locationFilter = document.getElementById('locationFilter');
        const table = document.getElementById('dataTable');
        const tbody = table.querySelector('tbody');
        
        function filterTable() {
            const searchTerm = searchInput.value.toLowerCase();
            const selectedLocation = locationFilter.value;
            const rows = tbody.querySelectorAll('tr');
            
            rows.forEach(row => {
                const filename = row.getAttribute('data-filename') || '';
                const location = row.getAttribute('data-location') || '';
                
                const matchesSearch = filename.includes(searchTerm);
                const matchesLocation = !selectedLocation || location === selectedLocation;
                
                if (matchesSearch && matchesLocation) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }
        
        searchInput.addEventListener('input', filterTable);
        locationFilter.addEventListener('change', filterTable);
        
        function resetFilters() {
            searchInput.value = '';
            locationFilter.value = '';
            filterTable();
        }
        
        // Ordenamiento de tabla
        let sortDirection = true;
        function sortTable(columnIndex) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            rows.sort((a, b) => {
                const aValue = a.cells[columnIndex].textContent.trim();
                const bValue = b.cells[columnIndex].textContent.trim();
                
                if (sortDirection) {
                    return aValue.localeCompare(bValue);
                } else {
                    return bValue.localeCompare(aValue);
                }
            });
            
            sortDirection = !sortDirection;
            
            rows.forEach(row => tbody.appendChild(row));
        }
        
        // Copiar ruta al portapapeles
        function copyPath(path) {
            navigator.clipboard.writeText(path).then(() => {
                alert('Ruta copiada al portapapeles');
            });
        }
    </script>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    if len(sys.argv) < 2:
        print("Uso: ./metadata_audiomoth.sh <directorio|archivo.wav> [salida.html]")
        print("\nEjemplos:")
        print("  ./metadata_audiomoth.sh AUdioMothRecs_LunaCaptiva/")
        print("  ./metadata_audiomoth.sh AUdioMothRecs_LunaCaptiva/ reporte.html")
        print("  ./metadata_audiomoth.sh . reporte_completo.html")
        print("  ./metadata_audiomoth.sh archivo.wav")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    # Determinar archivo de salida
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        # Si el input_path es el directorio actual, guardar en el directorio actual
        # Si es un subdirectorio, guardar en el directorio actual también
        output_file = "audiomoth_reporte.html"
    
    # Convertir output_file a ruta absoluta si no lo es
    if not os.path.isabs(output_file):
        output_file = os.path.abspath(output_file)
    
    print(f"🔍 Buscando archivos WAV en: {input_path}")
    wav_files = find_wav_files(input_path)
    
    if not wav_files:
        print("❌ No se encontraron archivos WAV")
        sys.exit(1)
    
    print(f"📁 Encontrados {len(wav_files)} archivos WAV")
    print("⚙️  Procesando archivos...")
    
    results = []
    for i, wav_file in enumerate(wav_files, 1):
        print(f"  [{i}/{len(wav_files)}] {Path(wav_file).name}")
        result = process_wav_file(wav_file)
        results.append(result)
    
    print(f"\n📊 Generando reporte HTML: {output_file}")
    generate_html(results, output_file)
    
    output_dir = os.path.dirname(output_file)
    output_basename = os.path.basename(output_file)
    
    print(f"✅ ¡Completado! Archivo generado en:")
    print(f"   {output_file}")
    print(f"\n💡 Para reproducir archivos localmente:")
    print(f"   1. Navega a: {output_dir}")
    print(f"   2. Ejecuta: python3 -m http.server 8000")
    print(f"   3. Abre: http://localhost:8000/{output_basename}")
    print(f"\n   O simplemente ejecuta desde el directorio del reporte:")
    print(f"   cd '{output_dir}' && python3 audiomoth_server.py")
    
    errors = sum(1 for r in results if r.get('error'))
    if errors > 0:
        print(f"⚠️  {errors} archivos con errores")


if __name__ == "__main__":
    main()
PYTHON_SCRIPT
