// Stage 3: Report Damage form behaviour - image preview, Leaflet location
// picker, optional GPS button, and a client-side guard against
// duplicate submissions from repeated button clicks.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("reportForm");
  if (!form) return; // not on the report page

  // --- Image preview ---
  const photoInput = document.getElementById("photo");
  const previewWrap = document.getElementById("imagePreviewWrap");
  const previewImg = document.getElementById("imagePreview");

  photoInput.addEventListener("change", () => {
    const file = photoInput.files && photoInput.files[0];
    if (!file) {
      previewWrap.classList.add("d-none");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImg.src = e.target.result;
      previewWrap.classList.remove("d-none");
    };
    reader.readAsDataURL(file);
  });

  // --- Leaflet map location picker ---
  const defaultCenter = [17.3297, 76.8343]; // Kalaburagi, Karnataka as a sensible default
  const map = L.map("reportMap").setView(defaultCenter, 13);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const latInput = document.getElementById("latitude");
  const lngInput = document.getElementById("longitude");
  const coordsText = document.getElementById("mapCoordsText");
  let marker = null;

  function setLocation(lat, lng) {
    latInput.value = lat.toFixed(6);
    lngInput.value = lng.toFixed(6);
    coordsText.textContent = `Selected location: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;

    if (marker) {
      marker.setLatLng([lat, lng]);
    } else {
      marker = L.marker([lat, lng]).addTo(map);
    }
  }

  // Restore a previously selected point (e.g. after a validation error).
  if (latInput.value && lngInput.value) {
    const lat = parseFloat(latInput.value);
    const lng = parseFloat(lngInput.value);
    if (!Number.isNaN(lat) && !Number.isNaN(lng)) {
      map.setView([lat, lng], 15);
      setLocation(lat, lng);
    }
  }

  map.on("click", (e) => {
    setLocation(e.latlng.lat, e.latlng.lng);
  });

  // --- Optional GPS button ---
  document.getElementById("gpsButton").addEventListener("click", () => {
    if (!navigator.geolocation) {
      coordsText.textContent = "Your browser doesn't support location access. Please click the map instead.";
      return;
    }
    coordsText.textContent = "Requesting your location...";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        map.setView([latitude, longitude], 16);
        setLocation(latitude, longitude);
      },
      () => {
        coordsText.textContent = "Couldn't get your location. Please click the map to select it manually.";
      }
    );
  });

  // --- Prevent duplicate submissions from repeated clicks ---
  const submitBtn = document.getElementById("submitBtn");
  const submitBtnText = document.getElementById("submitBtnText");
  const submitSpinner = document.getElementById("submitSpinner");

  form.addEventListener("submit", (e) => {
    if (!latInput.value || !lngInput.value) {
      e.preventDefault();
      coordsText.textContent = "Please select a location on the map before submitting.";
      coordsText.classList.add("text-danger");
      return;
    }
    if (submitBtn.disabled) {
      e.preventDefault();
      return;
    }
    submitBtn.disabled = true;
    submitBtnText.textContent = "Submitting...";
    submitSpinner.classList.remove("d-none");
  });
});