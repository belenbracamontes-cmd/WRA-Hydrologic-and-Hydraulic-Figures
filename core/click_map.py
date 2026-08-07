"""A click-to-drop-a-pin map widget, built as a Streamlit Custom
Component v2 (CCv2) since no native Streamlit widget exposes raw map
click coordinates.

Why this needs a custom component: ``st.pydeck_chart``'s ``on_select``
only reports *picks* on existing, already-rendered pickable objects (its
``PydeckState.selection`` schema is keyed by layer id + object index) --
there is no event for a click on empty map area returning a latitude/
longitude, which is what "drop a pin anywhere" needs. deck.gl itself does
expose that (an ``onClick`` handler's ``info.coordinate`` fires for any
map click, picked or not), but Streamlit's pydeck wrapper doesn't surface
it. Leaflet (loaded from a CDN inside this component, MIT-licensed, no
API key) fires exactly that plain click-anywhere event, so this widget
uses it instead of pydeck.

CSS is injected directly into the component's shadow root (not
document.head) since Shadow DOM does not let page-level stylesheets
penetrate into it -- Leaflet's own JS library, unlike its CSS, is loaded
onto ``window`` once and shared across every instance of this widget on
the page.
"""

import streamlit as st

_HTML = """<div id="map-root" style="width:100%;height:500px;border-radius:8px;overflow:hidden;"></div>"""

_JS = r"""
function ensureLeafletCss(root) {
  if (root.querySelector('link[data-leaflet-css]')) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
  link.setAttribute('data-leaflet-css', '1');
  root.appendChild(link);
}

function ensureLeafletJs(callback) {
  if (window.L) { callback(); return; }
  if (window.__leafletLoading) { window.__leafletLoading.push(callback); return; }
  window.__leafletLoading = [callback];
  const script = document.createElement('script');
  script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
  script.onload = () => {
    const cbs = window.__leafletLoading || [];
    window.__leafletLoading = null;
    cbs.forEach((cb) => cb());
  };
  document.head.appendChild(script);
}

// Per-instance map state, keyed by parentElement (a ShadowRoot here) so
// multiple mounted instances of this component never collide.
window.__clickMapInstances = window.__clickMapInstances || new WeakMap();

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const instances = window.__clickMapInstances;

  ensureLeafletCss(parentElement);

  function render() {
    let inst = instances.get(parentElement);
    if (!inst) {
      const mapDiv = parentElement.querySelector('#map-root');
      const map = L.map(mapDiv).setView([data.center.lat, data.center.lon], data.zoom);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
      }).addTo(map);
      const markersLayer = L.layerGroup().addTo(map);
      map.on('click', (e) => {
        setTriggerValue('clicked', { lat: e.latlng.lat, lon: e.latlng.lng });
      });
      inst = { map, markersLayer, boundsLayer: null, lastViewSignal: null };
      instances.set(parentElement, inst);
    }

    inst.markersLayer.clearLayers();
    (data.pins || []).forEach((p) => {
      L.circleMarker([p.lat, p.lon], {
        radius: 8,
        color: '#fff',
        weight: 1.5,
        fillColor: p.color || '#D4822B',
        fillOpacity: 0.9,
      }).bindTooltip(p.label || '').addTo(inst.markersLayer);
    });

    if (!inst.boundsLayer && data.bounds) {
      inst.boundsLayer = L.rectangle(
        [[data.bounds.min_lat, data.bounds.min_lon], [data.bounds.max_lat, data.bounds.max_lon]],
        { color: '#888888', weight: 1.5, fill: false, dashArray: '4 4' }
      ).addTo(inst.map);
    }

    if (data.view_signal !== inst.lastViewSignal) {
      inst.map.setView([data.center.lat, data.center.lon], data.zoom);
      inst.lastViewSignal = data.view_signal;
    }

    setTimeout(() => inst.map.invalidateSize(), 0);
  }

  if (window.L) {
    render();
  } else {
    ensureLeafletJs(render);
  }
}
"""

_CLICK_MAP = st.components.v2.component("wra_click_map", html=_HTML, js=_JS)


def render_click_map(*, center, zoom, pins, bounds, view_signal, key, height=500):
    """Render a click-to-drop-a-pin map.

    center -- {"lat": float, "lon": float}, the initial/forced map center.
    zoom -- initial/forced zoom level.
    pins -- list of {"lat", "lon", "label", "color"} dicts to draw as
        circle markers.
    bounds -- optional {"min_lat", "max_lat", "min_lon", "max_lon"} dict
        drawn once as a dashed reference rectangle (e.g. a dataset's
        coverage extent), or None to skip it.
    view_signal -- any hashable value; change it (e.g. after a "Zoom to
        this pin" button) to force the map to re-center/zoom without
        fighting the user's own pan/zoom the rest of the time.
    key -- Streamlit widget key for this map instance.

    Returns the dict the user clicked on the map this run, as
    {"lat": float, "lon": float}, or None if nothing was clicked this
    run (clicks are one-shot triggers -- see CCv2 state-sync docs).
    """
    result = _CLICK_MAP(
        key=key,
        data={"center": center, "zoom": zoom, "pins": pins, "bounds": bounds, "view_signal": view_signal},
        on_clicked_change=lambda: None,
    )
    return result.clicked
