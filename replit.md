# NetCDF Weather Data Visualizer

## Overview

This is a Flask-based web application designed to visualize weather and climate data from NetCDF files. The application allows users to upload NetCDF files through a drag-and-drop interface and provides interactive visualizations including maps, charts, and time series analysis. The tool is built to handle large climate datasets (up to 100MB) and extract coordinate and variable information for comprehensive data exploration.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Technology Stack**: HTML5, Bootstrap 5, JavaScript, Plotly.js
- **UI Components**: Drag-and-drop file upload interface with visual feedback states
- **Visualization Libraries**: 
  - Plotly.js for interactive charts and time series plots
  - Folium for interactive maps (server-side rendered)
- **Responsive Design**: Bootstrap-based responsive layout for cross-device compatibility

### Backend Architecture
- **Framework**: Flask (Python web framework)
- **File Handling**: Werkzeug for secure file upload processing
- **Data Processing Pipeline**:
  - xarray for NetCDF file reading and manipulation
  - numpy for numerical computations
  - pandas for data analysis and transformation
- **Session Management**: Global variables for current dataset storage (development setup)
- **File Storage**: Local filesystem uploads directory with security validation

### Data Processing
- **NetCDF Support**: Full xarray integration for reading multi-dimensional climate data
- **Data Extraction**: Automatic coordinate and variable information extraction
- **Coordinate Systems**: Support for spatial (lat/lon) and temporal dimensions
- **Variable Analysis**: Dynamic detection of data variables with dimensional metadata

### Security and Validation
- **File Type Validation**: Restricted to .nc (NetCDF) files only
- **File Size Limits**: 100MB maximum upload size
- **Secure Filename Handling**: Werkzeug secure_filename for safe file processing
- **Environment Configuration**: Environment-based secret key management

## External Dependencies

### Core Python Libraries
- **Flask**: Web framework for application structure and routing
- **xarray**: NetCDF file handling and multi-dimensional data processing
- **numpy**: Numerical computing and array operations
- **pandas**: Data manipulation and analysis

### Visualization Dependencies
- **Plotly**: Interactive charting and graphing (client-side JavaScript)
- **Folium**: Interactive map generation with Leaflet.js backend
- **Branca**: HTML/CSS/JavaScript generation for Folium maps

### Frontend Dependencies
- **Bootstrap 5**: CSS framework for responsive UI components
- **Plotly.js**: Client-side JavaScript library for interactive visualizations

### Development Dependencies
- **Werkzeug**: WSGI utilities and secure file handling
- **OS/JSON**: Standard library modules for system operations and data serialization