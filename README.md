# AudioMoth Processing Repository

## English Description

This repository contains a comprehensive AudioMoth data processing pipeline designed to analyze and visualize acoustic recordings from AudioMoth devices. The system transforms raw WAV audio files into interactive web galleries with spectrograms and metadata.

### 🎯 Key Components

#### **Master Processing Script** (`master_script.sh`)
- **Orchestrates** the entire processing pipeline
- **Handles** batch processing of AudioMoth WAV files with `YYYYMMDD_HHMMSS` naming convention
- **Validates** input files and checks for required dependencies
- **Provides** colored terminal output with progress indicators
- **Includes** error handling and comprehensive logging

#### **Enhanced HTML Gallery Generator** (`enhanced_html_generator.sh`)
- **Creates** sophisticated interactive web galleries
- **Extracts** detailed metadata from WAV files using `ffprobe` and `jq`
- **Features** GPS coordinate entry and storage system
- **Implements** advanced filtering and search capabilities
- **Generates** responsive, modern web interfaces with glassmorphism design

### ✨ Features

- **📊 Spectrogram Generation**: Creates both thumbnail images (256x144px) and full MP4 video spectrograms
- **🔍 Metadata Extraction**: Automatically extracts duration, file size, bitrate, device information, and comments from audio files
- **📍 GPS Integration**: Allows manual GPS coordinate entry with Google Maps integration and local storage
- **🎨 Interactive Gallery**: Modern web interface with lightbox video viewing, search functionality, and filtering options
- **📱 Responsive Design**: Mobile-friendly interface with dark theme and smooth animations
- **⚡ Batch Processing**: Handles multiple files efficiently with progress tracking

### 🎵 Use Cases
- Bioacoustic research and wildlife monitoring
- Environmental sound analysis
- Long-term acoustic monitoring projects
- Educational demonstrations of acoustic data

### 🛠️ Technical Stack
- **Shell Scripting**: Bash for pipeline orchestration
- **Audio Processing**: FFmpeg for spectrogram generation and metadata extraction
- **Web Technologies**: HTML5, CSS3, JavaScript for interactive galleries
- **Data Storage**: LocalStorage for GPS coordinates
- **Styling**: Modern CSS with glassmorphism effects

---

## Descripción en Español

Este repositorio contiene un pipeline completo de procesamiento de datos de AudioMoth diseñado para analizar y visualizar grabaciones acústicas de dispositivos AudioMoth. El sistema transforma archivos de audio WAV en bruto en galerías web interactivas con espectrogramas y metadatos.

### 🎯 Componentes Principales

#### **Script de Procesamiento Principal** (`master_script.sh`)
- **Orquesta** todo el pipeline de procesamiento
- **Maneja** el procesamiento en lotes de archivos WAV de AudioMoth con convención de nomenclatura `YYYYMMDD_HHMMSS`
- **Valida** archivos de entrada y verifica dependencias requeridas
- **Proporciona** salida de terminal colorizada con indicadores de progreso
- **Incluye** manejo de errores y registro exhaustivo

#### **Generador de Galería HTML Mejorado** (`enhanced_html_generator.sh`)
- **Crea** galerías web interactivas sofisticadas
- **Extrae** metadatos detallados de archivos WAV usando `ffprobe` y `jq`
- **Incluye** sistema de entrada y almacenamiento de coordenadas GPS
- **Implementa** capacidades avanzadas de filtrado y búsqueda
- **Genera** interfaces web modernas y responsivas con diseño glassmorphism

### ✨ Características

- **📊 Generación de Espectrogramas**: Crea tanto imágenes en miniatura (256x144px) como espectrogramas completos en video MP4
- **🔍 Extracción de Metadatos**: Extrae automáticamente duración, tamaño de archivo, tasa de bits, información del dispositivo y comentarios de archivos de audio
- **📍 Integración GPS**: Permite entrada manual de coordenadas GPS con integración de Google Maps y almacenamiento local
- **🎨 Galería Interactiva**: Interfaz web moderna con visualización de video en lightbox, funcionalidad de búsqueda y opciones de filtrado
- **📱 Diseño Responsivo**: Interfaz amigable para móviles con tema oscuro y animaciones suaves
- **⚡ Procesamiento en Lotes**: Maneja múltiples archivos eficientemente con seguimiento de progreso

### 🎵 Casos de Uso
- Investigación bioacústica y monitoreo de vida silvestre
- Análisis de sonidos ambientales
- Proyectos de monitoreo acústico a largo plazo
- Demostraciones educativas de datos acústicos

### 🛠️ Stack Técnico
- **Scripting de Shell**: Bash para orquestación del pipeline
- **Procesamiento de Audio**: FFmpeg para generación de espectrogramas y extracción de metadatos
- **Tecnologías Web**: HTML5, CSS3, JavaScript para galerías interactivas
- **Almacenamiento de Datos**: LocalStorage para coordenadas GPS
- **Estilizado**: CSS moderno con efectos glassmorphism

---

## 📁 Repository Structure

```
audiomoth-processing/
├── master_script.sh                    # Main orchestration script
├── enhanced_html_generator.sh          # Advanced gallery generator
├── make-spectrogram-thumbnail-fixed.sh # Thumbnail generation
├── make-spectrogram-movie-fixed.sh     # Video spectrogram creation
├── make-html-lightbox-table-fixed.sh   # Basic HTML table generator
├── spectrogram-table.css               # Gallery styling
├── perfundo.min.css                    # Lightbox CSS
└── README.md                           # Documentation
```

## 🚀 Quick Start

1. **Make scripts executable**:
   ```bash
   chmod +x *.sh
   ```

2. **Run the master script**:
   ```bash
   ./master_script.sh /path/to/audiomoth/*.WAV
   ```

3. **Open the generated gallery**:
   ```bash
   open index.html
   ```

## 📋 Requirements

- **FFmpeg**: For audio processing and spectrogram generation
- **jq**: For JSON metadata parsing
- **Bash**: Shell environment (Linux/macOS)
- **Modern web browser**: For viewing the interactive gallery

## 🎨 Gallery Features

- **🔍 Search**: Filter by filename, comment, or device
- **📂 Filters**: View all recordings, those with comments, GPS data, or long recordings
- **📍 GPS Tagging**: Manually add coordinates and view on Google Maps
- **🎬 Video Playback**: Click thumbnails to view spectrogram videos
- **📊 Statistics**: Real-time count of recordings, comments, and GPS data
- **💾 Data Persistence**: GPS coordinates saved in browser storage
