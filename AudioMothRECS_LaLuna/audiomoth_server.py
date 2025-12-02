#!/usr/bin/env python3
"""
Servidor HTTP simple con visualizador de archivos AudioMoth
Facilita la reproducción de archivos WAV directamente desde el navegador

Uso:
    python3 audiomoth_server.py [directorio] [--port PUERTO]
    
Ejemplos:
    python3 audiomoth_server.py
    python3 audiomoth_server.py /ruta/a/grabaciones
    python3 audiomoth_server.py --port 8080
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path
import webbrowser
from urllib.parse import unquote

PORT = 8000

class AudioMothHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador HTTP personalizado con soporte mejorado para archivos de audio"""
    
    def end_headers(self):
        # Agregar headers CORS para permitir acceso desde cualquier origen
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        # Cacheo para archivos de audio
        if self.path.endswith(('.wav', '.WAV', '.mp3', '.MP3')):
            self.send_header('Cache-Control', 'max-age=3600')
            # Habilitar streaming de audio
            self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        """Manejar solicitudes GET con casos especiales"""
        # Manejar solicitud de favicon
        if self.path == '/favicon.ico':
            self.send_response(204)  # No Content
            self.end_headers()
            return
        
        # Procesar normalmente otras solicitudes
        try:
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            # El cliente cerró la conexión (común en streaming de audio)
            # No es un error real, solo registramos silenciosamente
            pass
    
    def guess_type(self, path):
        """Mejorar la detección de tipos MIME para archivos de audio"""
        mimetype = super().guess_type(path)
        if path.lower().endswith('.wav'):
            return 'audio/wav'
        return mimetype
    
    def log_message(self, format, *args):
        """Log personalizado para mostrar solicitudes de archivos de audio"""
        try:
            # Filtrar solo solicitudes relevantes (evitar favicon, etc.)
            if args and len(args) > 0:
                request_path = str(args[0])
                if any(ext in request_path for ext in ['.wav', '.WAV', '.html', '.mp3', '.MP3']):
                    message = format % args
                    # Decodificar URL para mostrar nombres de archivo legibles
                    message = unquote(message)
                    print(f"[Servidor] {message}")
        except (TypeError, IndexError):
            # Ignorar errores de formato en logs
            pass
    
    def log_error(self, format, *args):
        """Suprimir errores de BrokenPipe y ConnectionReset en logs"""
        # Solo mostrar errores reales, no los de conexión interrumpida
        if args and len(args) > 0:
            error_msg = str(args[0]) if args else format
            if 'Broken pipe' in error_msg or 'Connection reset' in error_msg:
                return  # Ignorar estos errores silenciosamente
        # Mostrar otros errores normalmente
        super().log_error(format, *args)


def find_html_report(directory='.'):
    """Busca el archivo HTML del reporte en el directorio y subdirectorios"""
    path = Path(directory)
    
    # Primero buscar en el directorio actual
    patterns = ['audiomoth_reporte.html', 'reporte.html', '*audiomoth*.html']
    
    for pattern in patterns:
        matches = list(path.glob(pattern))
        if matches:
            return matches[0].name
    
    # Si no se encuentra, buscar en subdirectorios (máximo 2 niveles)
    for pattern in patterns:
        matches = list(path.glob(f'*/{pattern}'))
        if matches:
            rel_path = matches[0].relative_to(path)
            return str(rel_path)
        
        matches = list(path.glob(f'*/*/{pattern}'))
        if matches:
            rel_path = matches[0].relative_to(path)
            return str(rel_path)
    
    return None


def count_wav_files(directory='.'):
    """Cuenta archivos WAV en el directorio"""
    path = Path(directory)
    return len(list(path.rglob('*.wav'))) + len(list(path.rglob('*.WAV')))


def main():
    # Determinar directorio de trabajo
    if len(sys.argv) > 1:
        directory = sys.argv[1]
        if not os.path.isdir(directory):
            print(f"❌ Error: '{directory}' no es un directorio válido")
            sys.exit(1)
        os.chdir(directory)
    else:
        directory = os.getcwd()
    
    print("=" * 70)
    print("🎵 Servidor AudioMoth - Visualizador de Grabaciones")
    print("=" * 70)
    print(f"\n📁 Directorio: {os.getcwd()}")
    
    # Buscar archivos
    wav_count = count_wav_files()
    html_report = find_html_report()
    
    print(f"📊 Archivos WAV encontrados: {wav_count}")
    
    if html_report:
        print(f"📄 Reporte encontrado: {html_report}")
    else:
        print("⚠️  No se encontró reporte HTML. Genera uno primero con:")
        print("   ./metadata_audiomoth.sh <directorio>")
    
    print(f"\n🌐 Iniciando servidor en puerto {PORT}...")
    
    try:
        with socketserver.TCPServer(("", PORT), AudioMothHTTPRequestHandler) as httpd:
            print(f"✅ Servidor activo en: http://localhost:{PORT}/")
            
            if html_report:
                url = f"http://localhost:{PORT}/{html_report}"
                print(f"\n🎯 Visualizador: {url}")
                print("\n💡 Abriendo navegador automáticamente...")
                
                # Intentar abrir el navegador
                try:
                    webbrowser.open(url)
                except:
                    print("   (No se pudo abrir automáticamente)")
            
            print("\n📖 Instrucciones:")
            print("   • El servidor está ejecutándose")
            print("   • Puedes navegar por los archivos desde el navegador")
            print("   • Los archivos WAV se pueden reproducir directamente")
            print("   • Presiona Ctrl+C para detener el servidor")
            print("\n" + "=" * 70)
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n\n👋 Servidor detenido. ¡Hasta luego!")
        sys.exit(0)
    except OSError as e:
        if e.errno == 48 or "Address already in use" in str(e):
            print(f"\n❌ Error: El puerto {PORT} ya está en uso.")
            print("\nSoluciones:")
            print(f"   1. Detén el proceso que usa el puerto {PORT}")
            print("   2. Usa otro puerto: python servidor_audiomoth.py --port 8080")
            sys.exit(1)
        else:
            raise


if __name__ == "__main__":
    # Soporte para puerto personalizado
    if '--port' in sys.argv:
        try:
            port_idx = sys.argv.index('--port')
            PORT = int(sys.argv[port_idx + 1])
            # Remover argumentos de puerto para no confundir con directorio
            sys.argv = [sys.argv[0]] + [arg for i, arg in enumerate(sys.argv[1:], 1) 
                                         if i not in [port_idx, port_idx + 1]]
        except (ValueError, IndexError):
            print("❌ Error: Uso incorrecto de --port")
            print("   Ejemplo: python servidor_audiomoth.sh --port 8080")
            sys.exit(1)
    
    main()
