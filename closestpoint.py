# from shapely.geometry import Point, Polygon
# from shapely.ops import nearest_points
#
# poly = Polygon([(-0.1186133,51.511747),(-0.1185679,51.5117079),(-0.1185042,51.5117303),(-0.118551,51.5117752),(-0.1186133,51.511747)])
# point = Polygon([(-0.1203669,51.508505),(-0.1203394,51.5084929),(-0.1203194,51.5085104),(-0.1203469,51.5085226),(-0.1203669,51.508505)])
# # The points are returned in the same order as the input geometries:
# p1, p2 = nearest_points(poly, point)
# print(p1.wkt)
# # POINT (10.13793103448276 5.655172413793103)


# import sympy import Point, Polygon
from sympy import Point, Polygon

# creating points using Point()
p1, p2, p3, p4 = map(Point, [(0, 2), (0, 0), (1, 0), (1, 2)])

# creating polygon using Polygon()
poly = Polygon(p1, p2, p3, p4)

# using distance()
shortestDistance = poly.distance(Point(3, 5))

print(shortestDistance)