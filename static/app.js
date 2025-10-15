// static/app.js
window.currentTimeseries = {};
window.selectedLat = null;
window.selectedLon = null;
window.selectedStartDate = null;
window.selectedEndDate = null;
let uploadedFilepath = null;

// DOM elements
let dropZone, fileInput, loading, fileInfo, showFileInfo, visualizationSection, gridSection;

function initializeDOMElements() {
    dropZone = document.getElementById('dropZone');
    fileInput = document.getElementById('fileInput');
    loading = document.getElementById('loading');
    fileInfo = document.getElementById('fileInfo');
    showFileInfo = document.getElementById('showFileInfo');
    visualizationSection = document.getElementById('visualizationSection');
    gridSection = document.getElementById('gridSection');

    if (!dropZone || !fileInput || !loading || !fileInfo || !showFileInfo || !visualizationSection || !gridSection) {
        console.error("One or more DOM elements not found");
    }
}

// File upload handler (merged handleFileUpload and uploadDataset)
async function uploadDataset(file) {
    const filename = file.name.toLowerCase();
    if (!filename.endsWith('.nc') && !filename.endsWith('.grib') && !filename.endsWith('.grb')) {
        alert('Please select a NetCDF (.nc) or GRIB (.grib/.grb) file');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    loading.style.display = 'block';
    fileInfo.style.display = 'none';
    showFileInfo.style.display = 'none';
    visualizationSection.style.display = 'none';
    gridSection.style.display = 'none';

    try {
        const response = await fetch("/upload", { method: "POST", body: formData });
        const data = await response.json();
        //console.log("Upload response:", data);

        if (data.success) {
            uploadedFilepath = data.filepath;
            window.gridLats = data.gridLats;
            window.gridLons = data.gridLons;
            loading.style.display = 'none'; // <--- hide spinner
            // Display map
            displayMap(data.map_html);

            // Show fileInfo div and button
            fileInfo.style.display = "block";
            showFileInfo.style.display = "block";
        } else {
            alert(`Error: ${data.error || "Failed to upload file"}`);
            loading.style.display = "none";
        }
    } catch (err) {
        console.error("Error uploading file:", err);
        alert(`Network error: ${err.message}`);
        loading.style.display = "none";
    }
}

// Display file information
function displayFileInfo(info) {
    let html = '<div class="row">';
    html += '<div class="col-md-6">';
    html += '<h5>Coordinates</h5><ul>';
    for (const [coord, details] of Object.entries(info.coords)) {
        html += `<li><strong>${coord}:</strong> ${details.min.toFixed(4)} to ${details.max.toFixed(4)} (${details.size} points)</li>`;
    }
    html += '</ul></div>';

    html += '<div class="col-md-6">';
    html += '<h5>Variables</h5><ul>';
    for (const [varName, details] of Object.entries(info.variables)) {
        html += `<li><strong>${varName}:</strong> ${details.dims.join(' x ')} (${details.shape.join(' x ')})</li>`;
    }
    html += '</ul></div></div>';

    document.getElementById('fileDetails').innerHTML = html;
    fileInfo.style.display = 'block';
    showFileInfo.style.display = 'none';
}

// Display map
function displayMap(mapHtml) {
    document.getElementById('mapContainer').innerHTML = mapHtml;
    console.log("Map loaded. Points clickable via folium markers.");
    visualizationSection.style.display = 'block';
}

// Update charts
function updateCharts(charts) {
    const container = document.getElementById('chartsContainer');
    container.innerHTML = '';

    let chartCount = 0;
    for (const [varName, chartData] of Object.entries(charts)) {
        const chartDiv = document.createElement('div');
        chartDiv.id = `chart-${chartCount}`;
        chartDiv.className = 'chart-container';
        container.appendChild(chartDiv);

        Plotly.newPlot(chartDiv.id, chartData.data, chartData.layout).then(() => {
            const div = document.getElementById(chartDiv.id);

            // Add hover listener for horizontal line
            div.on('plotly_hover', function(eventData) {
                const yHover = eventData.points[0].y;

                Plotly.relayout(div, {
                    shapes: [{
                        type: 'line',
                        xref: 'x',
                        yref: 'y',
                        x0: eventData.points[0].xaxis.range[0],
                        x1: eventData.points[0].xaxis.range[1],
                        y0: yHover,
                        y1: yHover,
                        line: { color: 'blue', width: 2, dash: 'dot' }
                    }]
                });
            });

            // Remove line when unhover
            div.on('plotly_unhover', function() {
                Plotly.relayout(div, { shapes: [] });
            });
        });

        chartCount++;
    }

    visualizationSection.style.display = 'block';
}


// Handle grid point clicks
function handleGridClick(lat, lon) {
    console.log("handleGridClick called");
    gridSection.style.display = "block";

    if (window.parent && window.parent.document) {
        const coordsEl = window.parent.document.getElementById("selectedCoords");
        if (coordsEl) {
            coordsEl.textContent = `You clicked Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}`;
        }
    }

    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;

    const csvBtn = document.getElementById("downloadCsvBtn");
    csvBtn.style.display = "inline-block";
    csvBtn.onclick = () => downloadFile(lat, lon, window.selectedStartDate, window.selectedEndDate, "xlsx");

    const txtBtn = document.getElementById("downloadTxtBtn");
    txtBtn.style.display = "inline-block";
    txtBtn.onclick = () => downloadFile(lat, lon, window.selectedStartDate, window.selectedEndDate, "txt");

    const docxBtn = document.getElementById("downloadDocxBtn");
    docxBtn.style.display = "inline-block";
    docxBtn.onclick = () => downloadFile(lat, lon, window.selectedStartDate, window.selectedEndDate, "docx");

    window.selectedLat = lat;
    window.selectedLon = lon;

    const payload = { lat, lon };
    if (window.selectedStartDate && window.selectedEndDate) {
        payload.startDate = window.selectedStartDate;
        payload.endDate = window.selectedEndDate;
    }

    fetch('/get_timeseries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.success && data.charts) {
            window.currentTimeseries = data.charts;
            if (window.parent && typeof window.parent.updateCharts === 'function') {
                window.parent.updateCharts(data.charts);
            } else {
                updateCharts(data.charts);
            }
        } else {
            alert('Error: ' + (data.error || 'Unable to generate time series'));
        }
    })
    .catch(err => {
        console.error('Error fetching time series:', err);
        alert('Network error: ' + err.message);
    });
}

// Apply date range filter
async function applyDateRange() {
    const startInput = document.getElementById("startDate");
    const endInput = document.getElementById("endDate");

    if (!startInput || !endInput) {
        console.error("Date inputs not found");
        return;
    }

    const startDate = new Date(startInput.value);
    const endDate = new Date(endInput.value);

    if (isNaN(startDate) || isNaN(endDate)) {
        alert("Invalid start or end date");
        return;
    }

    if (!window.selectedLat || !window.selectedLon) {
        alert("Please select a grid point on the map first");
        return;
    }

    window.selectedStartDate = startDate.toISOString();
    window.selectedEndDate = endDate.toISOString();
    console.log("jsselected dates are: ", window.selectedStartDate, window.selectedEndDate);

    try {
        const response = await fetch('/get_timeseries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                lat: window.selectedLat,
                lon: window.selectedLon,
                startDate: startDate.toISOString(),
                endDate: endDate.toISOString()
            })
        });

        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const text = await response.text();
            console.error("Non-JSON response from server:", text);
            alert("Server error, see console");
            return;
        }

        const data = await response.json();
        if (data.success && data.charts) {
            window.currentTimeseries = data.charts;
            updateCharts(data.charts);
        } else {
            alert('Error: ' + (data.error || 'No charts returned'));
        }
    } catch (err) {
        console.error('Error applying date range:', err);
        alert('Network error: ' + err.message);
    }
}

// Find nearest grid point
function findNearestGridPoint(lat, lon) {
    let nearestLat = null;
    let nearestLon = null;
    let minDist = Infinity;

    window.gridLats.forEach(glat => {
        window.gridLons.forEach(glon => {
            let dLat = lat - glat;
            let dLon = lon - glon;
            let dist = dLat * dLat + dLon * dLon;
            if (dist < minDist) {
                minDist = dist;
                nearestLat = glat;
                nearestLon = glon;
            }
        });
    });
    return { lat: nearestLat, lon: nearestLon };
}

// Enable snap click for map
function enableSnapClick() {
    const iframe = document.querySelector("#mapContainer iframe");
    if (!iframe) return;

    iframe.addEventListener("load", () => {
        const innerDoc = iframe.contentDocument || iframe.contentWindow.document;
        const map = innerDoc.querySelector(".leaflet-container");

        if (!map) return;

        iframe.contentWindow.L.DomEvent.on(map, "click", (e) => {
            const lat = e.latlng.lat;
            const lon = e.latlng.lng;

            const nearest = findNearestGridPoint(lat, lon);
            if (nearest) {
                console.log("Snapped to:", nearest.lat, nearest.lon);
                handleGridClick(nearest.lat, nearest.lon);
            }
        });
    });
}

// Download file
function downloadFile(lat, lon, startDate, endDate, filetype) {
    fetch("/download_timeseries_csv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lon, startDate, endDate, filetype, 
            timeseriesData: window.currentTimeseries
         })
    })
    .then(response => {
        if (!response.ok) throw new Error("Download failed");
        return response.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const extensions = {
            csv: "timeseries.xlsx",
            txt: "timeseries.txt",
            docx: "timeseries.docx",
        };
        a.download = extensions[filetype] || "timeseries.xlsx";
        document.body.appendChild(a);
        a.click();
        a.remove();
    })
    .catch(err => console.error(err));
}

// static/app.js (relevant section only)
document.addEventListener("DOMContentLoaded", () => {
    initializeDOMElements();

    // Drag and drop functionality
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadDataset(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadDataset(e.target.files[0]);
        }
    });

    // Show file info button
    showFileInfo.addEventListener("click", async () => {
        console.log("Button clicked!");
        if (!uploadedFilepath) {
            console.log("No file uploaded, uploadedFilepath is:", uploadedFilepath);
            alert("No file uploaded yet");
            return;
        }

        const fileDetailsDiv = document.getElementById("fileDetails");
        fileDetailsDiv.textContent = "Loading...";
        try {
            console.log("Fetching file info for filepath:", uploadedFilepath);
            const res = await fetch("/extract_file_info", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filepath: uploadedFilepath })
            });
            //console.log("Response status:", res.status, "OK:", res.ok);
            //console.log("Response headers:", [...res.headers.entries()]);

            // Check if response is JSON
            const contentType = res.headers.get("content-type");

            if (!contentType || !contentType.includes("application/json")) {
                const text = await res.text();
                console.error("Non-JSON response:", text);
                fileDetailsDiv.textContent = `Error: Non-JSON response from server`;
                fileInfo.style.display = "block";
                return;
            }

            const data = await res.json();
            //console.log("Response data:", data);
            if (data.success) {
                displayFileInfo(data);
                fileInfo.style.display = "block";
                showFileInfo.style.display = "none";
            } else {
                fileDetailsDiv.textContent = `Error10: ${data.error || "Failed to load file info"}`;
                fileInfo.style.display = "block";
            }
        } catch (err) {
            console.error("Error fetching file info:", err);
            fileDetailsDiv.textContent = `Network error: ${err.message}`;
            fileInfo.style.display = "block";
        }
    });

    // Initialize map click handling
    enableSnapClick();
});

// Global function assignments
window.handleGridClick = handleGridClick;
window.applyDateRange = applyDateRange;
window.uploadDataset = uploadDataset;
window.displayFileInfo = displayFileInfo;
window.updateCharts = updateCharts;