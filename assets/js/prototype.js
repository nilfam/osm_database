import {postRequest} from './ajax-handler';
import {deepCopy} from "./utils";

require('bootstrap-select');
require('jquery-ui/ui/widgets/autocomplete');
let map;
let zoomLevel = 13;
let currentRelatum = null;
let currentLocatums = null;
let currentVicinity = null;

let $relatum = $('#relatum');
let $submitBtn = $('#submitBtn');
let $locatum = $('#locatum');
let $prep = $('#preposition');

function onEachFeature(feature, layer) {
    var namePart = "<p>Name: $name$ </p>";
    var distPart = "<p>Distance to relatum: $dist$ </p>";

    var popupContent = [];

    if (feature.properties) {
        if (feature.properties.name)
        {
            namePart = namePart.replace('$name$', feature.properties.name)
            popupContent.push(namePart)
        }
        if (feature.properties.dist)
        {
            distPart = distPart.replace('$dist$', feature.properties.dist)
            popupContent.push(distPart)
        }
    }

    popupContent = popupContent.join('')
    layer.bindPopup(popupContent);
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


let relatumGeoJsonTemplate = {
    "type": "Feature",
    'centroid': {
        'type': 'Point',
        'coordinates': null
    },
    'geometry': {
        'type': null,
        'coordinates': null
    },
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

function addRelatumToMap (geojson, name) {
    let geoJsonObject = deepCopy(relatumGeoJsonTemplate);
    geoJsonObject.centroid.coordinates = [geojson.lat, geojson.lon];
    geoJsonObject.geometry.type = geojson.geotype;
    geoJsonObject.geometry.coordinates = geojson.coordinates;
    geoJsonObject.properties.name = name;

    let geojsonObject = L.geoJSON(geoJsonObject, {
        style: function (feature) {
            return feature.properties && feature.properties.style;
        },

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

    geojsonObject.bindPopup(`
        <p>This is the relatum.</p>
        <p>Name: ${name}</p>
        <p>OSM Id: ${geojson.osm_id}</p>
        <p>OSM Type: ${geojson.osm_type}</p>
        <p>Geometry Type: ${geojson.geotype}</p>
        <p>Coordinates: [${geojson.lat} lat, ${geojson.lon} lon]</p>
    `);

    if (currentRelatum !== null)
        map.removeLayer(currentRelatum);
    geojsonObject.addTo(map);
    currentRelatum = geojsonObject;

    // Remove the vicinity and locatums
    if (currentVicinity !== null)
        map.removeLayer(currentVicinity);
    if (currentLocatums !== null)
        map.removeLayer(currentLocatums);
    currentVicinity = null;
    currentLocatums = null;

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
}

function addVicinityToMap (vicinity) {
    let geojsonObject = L.circle([vicinity.lat, vicinity.lon], vicinity.radius, {
        stroke: "#000",
        fillColor: "#B0DE5C",
        weight: 2,
        opacity: 1,
        fillOpacity: 0.1
    });

    geojsonObject.bindPopup(vicinity.explanation);

    if (currentVicinity !== null)
        map.removeLayer(currentVicinity);
    geojsonObject.addTo(map);
    currentVicinity = geojsonObject;

    map.removeLayer(currentRelatum);
    currentRelatum.addTo(map);

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
                    addRelatumToMap(geojson, ui.item.label);
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
                if (locatumArr.length === 0) {
                    if (currentLocatums !== null)
                        map.removeLayer(currentLocatums);
                    currentLocatums = null;
                    return;
                }
                let locatumCollectionGeoJson = deepCopy(locatumCollectionGeoJsonTemplate);
                let vicinity = null;
                $.each(locatumArr, function (_, geojson) {
                    if (geojson.id === 'vicinity')
                    {
                        if (vicinity !== null)
                            throw new Error('Two vicinity objects found in response');
                        vicinity = geojson;
                    }
                    else
                    {
                        let geoJsonObject = deepCopy(locatumGeoJsonTemplate);
                        geoJsonObject.geometry.coordinates = [geojson.lat, geojson.lon];
                        geoJsonObject.properties.name = geojson.name;
                        geoJsonObject.properties.dist = geojson.dist;
                        geoJsonObject.id = geojson.id;
                        locatumCollectionGeoJson.features.push(geoJsonObject)
                    }
                });

                if (vicinity === null)
                    throw new Error('No vicinity object found in response');
                addVicinityToMap(vicinity);
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
