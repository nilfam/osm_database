import {postRequest} from './ajax-handler';
import {deepCopy} from "./utils";

require('bootstrap-select');
require('jquery-ui/ui/widgets/autocomplete');
let map;
let zoomLevel = 13;
let currentRelatum = null;
let currentLocatums = null;
let $relatum = $('#relatum');
let $submitBtn = $('#submitBtn');
let $locatum = $('#locatum');
let $prep = $('#preposition');

function onEachFeature(feature, layer) {
    var popupContent = "<p>This OSM Entity is type " + feature.geometry.type + "</p>";

    if (feature.properties && feature.properties.name) {
        popupContent += feature.properties.name;
    }

    layer.bindPopup(popupContent);
}

let relatumGeoJsonTemplate = {
    "type": "Feature",
    "properties": {
        "name": null,
        "style": {
            weight: 2,
            color: "#999",
            opacity: 1,
            fillColor: "#B0DE5C",
            fillOpacity: 0.2
        }
    },
}

let locatumGeoJsonTemplate = {
    "geometry": {
        "type": "Point",
        "coordinates": null
    },
    "type": "Feature",
    "properties": {
        "name": null
    },
    "id": null
};

let locatumCollectionGeoJsonTemplate = {
    "type": "FeatureCollection",
    "features": []
};

function addRelatumToMap (geojson) {
    let geojsonObject = L.geoJSON(geojson, {
        style: function (feature) {
            return feature.properties && feature.properties.style;
        },

        onEachFeature: onEachFeature,

        pointToLayer: function (feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 8,
                fillColor: "#ff7800",
                color: "#000",
                weight: 1,
                opacity: 1,
                fillOpacity: 0.8
            });
        }
    });
    if (currentRelatum !== null)
        map.removeLayer(currentRelatum);
    geojsonObject.addTo(map);
    currentRelatum = geojsonObject;
    map.fitBounds(geojsonObject.getBounds());
}

function addLocatumsToMap (geojson) {
    let geojsonObject = L.geoJSON(geojson, {

		style: function (feature) {
			return feature.properties && feature.properties.style;
		},

		onEachFeature: onEachFeature,

		pointToLayer: function (feature, latlng) {
			return L.circleMarker(latlng, {
				radius: 8,
				fillColor: "#ff7800",
				color: "#000",
				weight: 1,
				opacity: 1,
				fillOpacity: 0.8
			});
		}
	});

    if (currentLocatums !== null)
        map.removeLayer(currentLocatums);
    geojsonObject.addTo(map);
    currentLocatums = geojsonObject;
    map.fitBounds(geojsonObject.getBounds());
}

// Init Open Street Maps
function initMap() {
    map = L.map('map');
    map.setView([51.5074889, -0.16223668308067218], zoomLevel);

    L.tileLayer('https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token=pk.eyJ1IjoiZnp5dWtpbyIsImEiOiJja3YzYW9lZWkwb3ZpMnZsMDAwdjR5emFsIn0.AJqr9Tgp0ASIsVlDcuJdag', {
        maxZoom: 18,
        attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
            'Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
        id: 'mapbox/light-v9',
        tileSize: 512,
        zoomOffset: -1
    }).addTo(map);
}

function decorateSelect() {
    $('.custom-select').selectpicker({
        noneSelectedText: '',
        size: 10,
        dropdownAlignRight: 'auto',
        selectOnTab: true,
        liveSearch: true,
        liveSearchStyle: 'startsWith',
        liveSearchNormalize: true
    });
}

function initAutocompleteForRelatum() {
    $relatum.autocomplete({
        // minimum number of entered characters before trying to search
        minLength: 2,
        // milliseconds to wait before trying to search
        delay: 500,
        source: function (request, response) {
            var searchTerm = request.term.toLowerCase();
            postRequest({
                requestSlug: 'osm_database/find-rel',
                data: {relatum: searchTerm},
                onSuccess(arr) {
                    response(arr);
                },
                immediate: true,
            });
        },
        focus: function (event, ui) {
            // Prevent autocomplete from updating the textbox
            event.preventDefault();
            // Manually update the textbox
            $(this).val(ui.item.label);
        },
        select: function (event, ui) {
            // Prevent autocomplete from updating the textbox
            event.preventDefault();
            // Manually update the textbox
            $(this).val(ui.item.label);

            $relatum.data('osmId', ui.item.osm_id);
            $relatum.data('osmType', ui.item.osm_type);

            map.flyTo([ui.item.lat, ui.item.lon], zoomLevel);

            postRequest({
                requestSlug: 'osm_database/get-geojson-info',
                data: {osm_id: ui.item.osm_id, osm_type: ui.item.osm_type},
                onSuccess(geojson) {
                    geojson = geojson[0]
                    let geoJsonObject = deepCopy(relatumGeoJsonTemplate);
                    geoJsonObject.centroid = geojson.centroid;
                    geoJsonObject.geometry = geojson.geometry;
                    geoJsonObject.properties.name = ui.item.label;
                    addRelatumToMap(geoJsonObject);
                },
                immediate: true,
            });

        },
    });
}

function initSubmitBtn () {
    $submitBtn.click(function (e) {
        let locatumType = $locatum.val();
        let prepType = $prep.val();
        let osmId = $relatum.data('osmId');
        let osmType = $relatum.data('osmType');

        e.preventDefault();
        postRequest({
            requestSlug: 'osm_database/find-locs',
            data: {loc_type: locatumType, osm_type: osmType, osm_id: osmId, preposition: prepType},
            onSuccess(locatumArr) {
                let locatumCollectionGeoJson = deepCopy(locatumCollectionGeoJsonTemplate);
                $.each(locatumArr, function (_, geojson) {
                    let geoJsonObject = deepCopy(locatumGeoJsonTemplate);
                    geoJsonObject.geometry.coordinates = [geojson.lat, geojson.lon];
                    geoJsonObject.properties.name = geojson.name;
                    geoJsonObject.id = geojson.id;
                    locatumCollectionGeoJson.features.push(geoJsonObject)
                });

                addLocatumsToMap(locatumCollectionGeoJson);
            },
            immediate: true,
        });
    });
}

export const run = function () {
    initMap();
    initAutocompleteForRelatum();
    initSubmitBtn();
    decorateSelect();
    return Promise.resolve();
};
