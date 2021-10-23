from osm_database.management.commands.find_nodes_within_vicinity import find_max_deviation
from osm_database.management.commands.util import extract_points_for_polygons, extract_points_for_multipolygons, \
    extract_points_for_point, extract_points_for_linestrings, extract_points_for_multilinestrings
from osm_database.model_utils import get_or_error
from osm_database.models import OsmEntity


__all__ = ['find_rel', 'find_locs', 'get_geojson_info']


def find_rel(request):
    relatum = get_or_error(request.POST, 'relatum')
    rel_objs = OsmEntity.objects.filter(
        # Boundary of London
        lat__gte=51.21635, lat__lte=51.76189, lon__gte=-0.93933, lon__lte=0.76355,
        display_name__icontains=relatum, geojson__type__in=['Polygon', 'MultiPolygon'])\
        .order_by('-importance').values_list('id', 'display_name', 'osm_id', 'osm_type', 'lat', 'lon')
    retval = []
    for id, dn, oid, otype, lat, lon in rel_objs:
        retval.append({'label': dn, 'osm_type': otype, 'osm_id': oid, 'lat': lat, 'lon': lon})

    return retval


def find_locs(request):
    loc_type = get_or_error(request.POST, 'loc_type')
    osm_type = get_or_error(request.POST, 'osm_type')
    osm_id = get_or_error(request.POST, 'osm_id')
    vicinity = 1000
    entities = OsmEntity.objects.filter(osm_id=osm_id, osm_type=osm_type)
    entity = entities.first()
    min_lat, max_lat, min_lon, max_lon = find_max_deviation(float(entity.lat), float(entity.lon), vicinity)
    possible_locs = OsmEntity.objects.filter(lat__gte=min_lat, lat__lte=max_lat, lon__gte=min_lon, lon__lte=max_lon,
                                             type=loc_type).values_list('id', 'display_name', 'lat', 'lon')

    retval = []
    for id, dn, lat, lon in possible_locs:
        if lat > 10:
            retval.append({'id': id, 'name': dn, 'lat': lon, 'lon': lat})
        else:
            retval.append({'id': id, 'name': dn, 'lat': lat, 'lon': lon})

    return retval



def swap_lon_lat_if_necessary(points):
    if len(points) == 0:
        return points
    lat, lon = points[0]
    if lat > 10:
        return [x[::-1] for x in points]
    return points


def get_geojson_info(request):
    osm_type = get_or_error(request.POST, 'osm_type')
    osm_id = get_or_error(request.POST, 'osm_id')
    entities = OsmEntity.objects.filter(osm_id=osm_id, osm_type=osm_type)
    entity = entities.first()
    entity_geojson_type = entity.geojson.type
    geojson_id = entity.geojson.id

    if entity_geojson_type == 'Point':
        geojson_to_point_id, point_ids_to_geopoints = extract_points_for_point(entities)
        points = point_ids_to_geopoints[geojson_to_point_id[geojson_id]]
        wkt_points = swap_lon_lat_if_necessary(points)

    elif entity_geojson_type == 'Polygon':
        geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(entities)
        points = ext_ring_ids_to_list_of_points[geojson_to_exterior_id[geojson_id]]
        wkt_points = swap_lon_lat_if_necessary(points)

    # elif entity_geojson_type == 'MultiPolygon':
    #     geojson_to_multipoly_id, multipoly_ids_to_list_of_points = extract_points_for_multipolygons(entities)
    #     multipoly_id = geojson_to_multipoly_id[geojson_id]
    #     points = multipoly_ids_to_list_of_points[multipoly_id]
    #     wkt_points = swap_lon_lat_if_necessary(points)

    elif entity_geojson_type == 'LineString':
        geojson_to_line_id, lines_ids_to_list_of_points = extract_points_for_linestrings(entities)
        line_id = geojson_to_line_id[geojson_id]
        points = lines_ids_to_list_of_points[line_id]
        wkt_points = swap_lon_lat_if_necessary(points)

    elif entity_geojson_type == 'MultiLineString':
        geojson_to_multiline_id, multiline_ids_to_list_of_points = extract_points_for_multilinestrings(entities)
        multiline_id = geojson_to_multiline_id[geojson_id]
        points = multiline_ids_to_list_of_points[multiline_id]
        wkt_points = swap_lon_lat_if_necessary(points)

    else:
        raise Exception('Unsupported type: ' + entity_geojson_type)


    retval = [{
        'centroid': {'type': 'Point', 'coordinates': [entity.lon, entity.lat]},
        'geometry': {
            'type': entity_geojson_type,
            'coordinates': [wkt_points]
        }
    }]

    return retval