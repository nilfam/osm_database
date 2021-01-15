from shapely import geometry, ops
from scipy.spatial import ConvexHull, convex_hull_plot_2d
import numpy as np
from pyhull.convex_hull import ConvexHull
# # create three lines
line_a = geometry.LineString([[53.2632383, -2.1235673], [53.2632601, -2.1237771], [53.2632728, -2.1239397], [53.2632862, -2.1241123]])
line_b = geometry.LineString([[53.263191, -2.1232018], [53.2632383, -2.1235673]])
line_c = geometry.LineString([[53.2633388, -2.1236225], [53.2633428, -2.1235921], [53.2633917, -2.1232927]])



multi_line = geometry.MultiLineString([line_a, line_b, line_c])
merged_line = ops.linemerge(multi_line)
print(merged_line)


# combine them into a multi-linestring

# import shapely.geometry
#
# # Make a MultiLineString to use for the example
# inlines = shapely.geometry.MultiLineString(
#     [shapely.geometry.LineString([(53.2632383, -2.1235673), (53.2632601, -2.1237771), (53.2632728, -2.1239397), (53.2632862, -2.1241123)]),
#      shapely.geometry.LineString([(53.263191, -2.1232018), (53.2632383, -2.1235673)]),
#      shapely.geometry.LineString([(53.2633388, -2.1236225), (53.2633428, -2.1235921), (53.2633917, -2.1232927)])]
# )
#
# # Put the sub-line coordinates into a list of sublists
# outcoords = [list(i.coords) for i in inlines]
#
# # Flatten the list of sublists and use it to make a new line
# outline = shapely.geometry.LineString([i for sublist in outcoords for i in sublist])
# print(outline)
