
// static/app.js
window.currentTimeseries = {}; 
window.selectedLat = null;
window.selectedLon = null;
window.selectedStartDate = null;
window.selectedEndDate = null;

// Handle grid point clicks
function handleGridClick(lat, lon) {
    console.log("handleGridClick called");
    document.getElementById("gridSection").style.display = "block";

    if (window.parent && window.parent.document) {
        const coordsEl = window.parent.document.getElementById("selectedCoords");
        if (coordsEl) {
            coordsEl.textContent = `You clicked Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}`;
        }
    }

    window.selectedLat = lat;
    window.selectedLon = lon;
    
    // Prepare request payload
    const payload = { lat, lon };
    if (window.selectedStartDate && window.selectedEndDate) {
        payload.startDate = window.selectedStartDate;
        payload.endDate   = window.selectedEndDate;
    }
    // Fetch full time series from Flask
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
window.handleGridClick = handleGridClick;

// Apply date range filter via server
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

    // Save global time range
    window.selectedStartDate = startDate.toISOString();
    window.selectedEndDate   = endDate.toISOString();
    console.log("jsselected dates are: ", window.selectedStartDate, window.selectedEndDate)
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
            if (typeof window.parent.updateCharts === 'function') {
                window.parent.updateCharts(data.charts);
            }
        } else {
            alert('Error: ' + (data.error || 'No charts returned'));
        }

    } catch (err) {
        console.error('Error applying date range:', err);
        alert('Network error: ' + err.message);
    }
}
window.applyDateRange = applyDateRange;


function findNearestGridPoint(lat, lon) {
    let nearestLat = null;
    let nearestLon = null;
    let minDist = Infinity;

    gridLats.forEach(glat => {
        gridLons.forEach(glon => {
            let dLat = lat - glat;
            let dLon = lon - glon;
            let dist = dLat * dLat + dLon * dLon; // squared distance
            if (dist < minDist) {
                minDist = dist;
                nearestLat = glat;
                nearestLon = glon;
            }
        });
    });
    return { lat: nearestLat, lon: nearestLon };
}

// Attach click listener to map
map.on('click', function(e) {
    const clickedLat = e.latlng.lat;
    const clickedLon = e.latlng.lng;

    const nearest = findNearestGridPoint(clickedLat, clickedLon);
    console.log("Snapped to nearest:", nearest);

    // Call your existing handler
    handleGridClick(nearest.lat, nearest.lon);
});

async function uploadDataset(formData) {
    const response = await fetch("/upload", {
        method: "POST",
        body: formData
    });
    const data = await response.json();

    displayMap(data.map_html);

    // Save grid coordinates globally
    window.gridLats = data.gridLats;
    window.gridLons = data.gridLons;
}


function enableSnapClick() {
    const iframe = document.querySelector("#mapContainer iframe");
    if (!iframe) return;

    iframe.addEventListener("load", () => {
        const innerDoc = iframe.contentDocument || iframe.contentWindow.document;
        const map = innerDoc.querySelector(".leaflet-container");

        if (!map) return;

        // Attach a click listener via Leaflet API
        iframe.contentWindow.L.DomEvent.on(map, "click", (e) => {
            const lat = e.latlng.lat;
            const lon = e.latlng.lng;

            const nearest = findNearestGridPoint(lat, lon);
            if (nearest) {
                const [snapLat, snapLon] = nearest;
                console.log("Snapped to:", snapLat, snapLon);

                // Act as if user clicked the marker
                handleGridClick(snapLat, snapLon);
            }
        });
    });
}

/*
function findNearestGridPoint(lat, lon) {
    if (!window.gridLats || !window.gridLons) return null;

    let bestDist = Infinity;
    let bestPoint = null;

    for (let i = 0; i < window.gridLats.length; i++) {
        for (let j = 0; j < window.gridLons.length; j++) {
            const dLat = lat - window.gridLats[i];
            const dLon = lon - window.gridLons[j];
            const dist = dLat * dLat + dLon * dLon;
            if (dist < bestDist) {
                bestDist = dist;
                bestPoint = [window.gridLats[i], window.gridLons[j]];
            }
        }
    }
    return bestPoint;
}
*/