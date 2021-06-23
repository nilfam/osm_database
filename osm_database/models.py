from django.db import models


class PointList(models.Model):
    pass


class GeoJSON(models.Model):
    type = models.CharField(max_length=255)


class Position(models.Model):
    id = models.BigIntegerField(primary_key=True, auto_created=False)
    lat = models.DecimalField(max_digits=22, decimal_places=18, null=False, blank=False)
    lon = models.DecimalField(max_digits=22, decimal_places=18, null=False, blank=False)


class Point(models.Model):
    # For type "Point", the "coordinates" member is a single position.
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    position = models.ForeignKey(Position, null=False, blank=False, on_delete=models.CASCADE)


class MultiPoint(models.Model):
    # For type "MultiPoint", the "coordinates" member is an array of positions.
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    coordinate = models.ForeignKey(Position, null=False, blank=False, on_delete=models.CASCADE)


class LineString(models.Model):
    # For type "LineString", the "coordinates" member is an array of two or more positions.
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    positions = models.ManyToManyField(Position)


class MultiLineString(models.Model):
    # For type "MultiLineString", the "coordinates" member is an array of LineString coordinate arrays.
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    linestrings = models.ManyToManyField(LineString)


class LinearRing(models.Model):
    # A linear ring is a closed LineString with four or more positions.
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    positions = models.ManyToManyField(Position)


class Polygon(models.Model):
    """
    To specify a constraint specific to Polygons, it is useful to introduce the concept of a linear ring:

   o  A linear ring is a closed LineString with four or more positions.

   o  The first and last positions are equivalent, and they MUST contain
      identical values; their representation SHOULD also be identical.

   o  A linear ring is the boundary of a surface or the boundary of a
      hole in a surface.

   o  A linear ring MUST follow the right-hand rule with respect to the
      area it bounds, i.e., exterior rings are counterclockwise, and
      holes are clockwise.

   Note: the [GJ2008] specification did not discuss linear ring winding
   order.  For backwards compatibility, parsers SHOULD NOT reject
   Polygons that do not follow the right-hand rule.

   Though a linear ring is not explicitly represented as a GeoJSON
   geometry type, it leads to a canonical formulation of the Polygon
   geometry type definition as follows:

   o  For type "Polygon", the "coordinates" member MUST be an array of
      linear ring coordinate arrays.

   o  For Polygons with more than one of these rings, the first MUST be
      the exterior ring, and any others MUST be interior rings.  The
      exterior ring bounds the surface, and the interior rings (if
      present) bound holes within the surface.    """
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    exterior_ring = models.ForeignKey(LinearRing, null=False, blank=False, on_delete=models.CASCADE, related_name="exterior")
    interior_rings = models.ManyToManyField(LinearRing, related_name="interiors")


class MultiPolygon(models.Model):
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)
    polygons = models.ManyToManyField(Polygon)


class OsmEntity(models.Model):
    osm_id = models.BigIntegerField(null=False, blank=False, unique=False, primary_key=True)
    osm_type = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    display_name = models.CharField(max_length=1024)
    place_id = models.IntegerField(null=False, blank=False)
    place_rank = models.IntegerField(null=True, blank=True)
    importance = models.FloatField(null=True, blank=True)
    lat = models.DecimalField(max_digits=22, decimal_places=18)
    lon = models.DecimalField(max_digits=22, decimal_places=18)
    left = models.FloatField(null=True, blank=True)
    bottom = models.FloatField(null=True, blank=True)
    right = models.FloatField(null=True, blank=True)
    top = models.FloatField(null=True, blank=True)
    geojson = models.ForeignKey(GeoJSON, null=False, blank=False, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('osm_type', 'osm_id')

    def __str__(self):
        return "ID: {} Type: {} Category: {} name={}"\
            .format(self.osm_id, self.type, self.category, self.display_name)


class TagName(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False, unique=True)


class TagValue(models.Model):
    value = models.CharField(max_length=1000, blank=False, null=False)


class Tag(models.Model):
    k = models.ForeignKey(TagName, blank=False, null=False, on_delete=models.CASCADE)
    v = models.ForeignKey(TagValue, blank=False, null=False, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('k', 'v')


class Node(models.Model):
    osm_id = models.BigIntegerField(null=False, blank=False, unique=True, primary_key=True)
    lat = models.DecimalField(max_digits=22, decimal_places=18)
    lon = models.DecimalField(max_digits=22, decimal_places=18)
    tags = models.ManyToManyField(Tag, related_name="interiors")

