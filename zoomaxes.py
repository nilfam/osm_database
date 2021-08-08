from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from matplotlib.path import Path
from matplotlib.axes import Axes
from matplotlib.axes._axes import _make_inset_locator
from matplotlib.text import Text
from matplotlib.transforms import Bbox, Transform, IdentityTransform, Affine2D
from matplotlib.backend_bases import RendererBase
import matplotlib._image as _image
import numpy as np


class TransformRenderer(RendererBase):
    """
    A matplotlib renderer which performs transforms to change the final location of plotted
    elements, and then defers drawing work to the original renderer.
    """
    def __init__(self, base_renderer: RendererBase, mock_transform: Transform, transform: Transform,
                 bounding_axes: Axes):
        """
        Constructs a new TransformRender.

        :param base_renderer: The renderer to use for finally drawing objects.
        :param mock_transform: The transform or coordinate space which all passed paths/triangles/images will be
                               converted to before being placed back into display coordinates by the main transform.
                               For example if the parent axes transData is passed, all objects will be converted to
                               the parent axes data coordinate space before being transformed via the main transform
                               back into coordinate space.
        :param transform: The main transform to be used for plotting all objects once converted into the mock_transform
                          coordinate space. Typically this is the child axes data coordinate space (transData).
        :param bounding_axes: The axes to plot everything within. Everything outside of this axes will be clipped.
        """
        super().__init__()
        self.__renderer = base_renderer
        self.__mock_trans = mock_transform
        self.__core_trans = transform
        self.__bounding_axes = bounding_axes

    def _get_axes_display_box(self) -> Bbox:
        """
        Private method, get the bounding box of the child axes in display coordinates.
        """
        return self.__bounding_axes.patch.get_bbox().transformed(self.__bounding_axes.transAxes)

    def _get_transfer_transform(self, orig_transform):
        """
        Private method, returns the transform which translates and scales coordinates as if they were originally
        plotted on the child axes instead of the parent axes.

        :param orig_transform: The transform that was going to be originally used by the object/path/text/image.

        :return: A matplotlib transform which goes from original point data -> display coordinates if the data was
                 originally plotted on the child axes instead of the parent axes.
        """
        # We apply the original transform to go to display coordinates, then apply the parent data transform inverted
        # to go to the parent axes coordinate space (data space), then apply the child axes data transform to
        # go back into display space, but as if we originally plotted the artist on the child axes....
        return orig_transform + self.__mock_trans.inverted() + self.__core_trans

    # We copy all of the properties of the renderer we are mocking, so that artists plot themselves as if they were
    # placed on the original renderer.
    @property
    def height(self):
        return self.__renderer.get_canvas_width_height()[1]

    @property
    def width(self):
        return self.__renderer.get_canvas_width_height()[0]

    def get_text_width_height_descent(self, s, prop, ismath):
        return self.__renderer.get_text_width_height_descent(s, prop, ismath)

    def get_canvas_width_height(self):
        return self.__renderer.get_canvas_width_height()

    def get_texmanager(self):
        return self.__renderer.get_texmanager()

    def get_image_magnification(self):
        return self.__renderer.get_image_magnification()

    def _get_text_path_transform(self, x, y, s, prop, angle, ismath):
        return self.__renderer._get_text_path_transform(x, y, s, prop, angle, ismath)

    def option_scale_image(self):
        return False

    def points_to_pixels(self, points):
        return self.__renderer.points_to_pixels(points)

    def flipy(self):
        return self.__renderer.flipy()

    # Actual drawing methods below:

    def draw_path(self, gc, path: Path, transform: Transform, rgbFace=None):
        # Convert the path to display coordinates, but if it was originally drawn on the child axes.
        path = path.deepcopy()
        path.vertices = self._get_transfer_transform(transform).transform(path.vertices)
        bbox = self._get_axes_display_box()

        # We check if the path intersects the axes box at all, if not don't waste time drawing it.
        if(not path.intersects_bbox(bbox, True)):
            return

        # Change the clip to the sub-axes box
        gc.set_clip_rectangle(bbox)

        self.__renderer.draw_path(gc, path, IdentityTransform(), rgbFace)

    def _draw_text_as_path(self, gc, x, y, s: str, prop, angle, ismath):
        # If the text field is empty, don't even try rendering it...
        if((s is None) or (s.strip() == "")):
            return
        # Call the super class instance, which works for all cases except one checked above... (Above case causes error)
        super()._draw_text_as_path(gc, x, y, s, prop, angle, ismath)

    def draw_gouraud_triangle(self, gc, points, colors, transform):
        # Pretty much identical to draw_path, transform the points and adjust clip to the child axes bounding box.
        points = self._get_transfer_transform(transform).transform(points)
        path = Path(points, closed=True)
        bbox = self._get_axes_display_box()

        if(not path.intersects_bbox(bbox, True)):
            return

        gc.set_clip_rectangle(bbox)

        self.__renderer.draw_gouraud_triangle(gc, path.vertices, colors, IdentityTransform())

    # Images prove to be especially messy to deal with...
    def draw_image(self, gc, x, y, im, transform=None):
        mag = self.get_image_magnification()
        shift_data_transform = self._get_transfer_transform(IdentityTransform())
        axes_bbox = self._get_axes_display_box()
        # Compute the image bounding box in display coordinates.... Image arrives pre-magnified.
        img_bbox_disp = Bbox.from_bounds(x, y, im.shape[1], im.shape[0])
        # Now compute the output location, clipping it with the final axes patch.
        out_box = img_bbox_disp.transformed(shift_data_transform)
        clipped_out_box = Bbox.intersection(out_box, axes_bbox)

        if(clipped_out_box is None):
            return

        # We compute what the dimensions of the final output image within the sub-axes are going to be.
        x, y, out_w, out_h = clipped_out_box.bounds
        out_w, out_h = int(np.ceil(out_w * mag)), int(np.ceil(out_h * mag))

        if((out_w <= 0) or (out_h <= 0)):
            return

        # We can now construct the transform which converts between the original image (a 2D numpy array which starts
        # at the origin) to the final zoomed image (also a 2D numpy array which starts at the origin).
        img_trans = (
            Affine2D().scale(1/mag, 1/mag).translate(img_bbox_disp.x0, img_bbox_disp.y0)
            + shift_data_transform
            + Affine2D().translate(-clipped_out_box.x0, -clipped_out_box.y0).scale(mag, mag)
        )

        # We resize and zoom the original image onto the out_arr.
        out_arr = np.zeros((out_h, out_w, im.shape[2]), dtype=im.dtype)
        _image.resample(im, out_arr, img_trans, _image.NEAREST, alpha=1)
        _image.resample(im[:, :, 3], out_arr[:, :, 3], img_trans, _image.NEAREST, alpha=1)

        gc.set_clip_rectangle(clipped_out_box)

        x, y = clipped_out_box.x0, clipped_out_box.y0

        if(self.option_scale_image()):
            self.__renderer.draw_image(gc, x, y, out_arr, None)
        else:
            self.__renderer.draw_image(gc, x, y, out_arr)

class ZoomViewAxes(Axes):
    """
    A zoom axes which automatically displays all of the elements it is currently zoomed in on. Does not require
    Artists to be plotted twice.
    """
    def __init__(self, zoom_ratio, axes_of_zoom: Axes, rect: Bbox, transform = None, zorder = 5, **kwargs):
        """
        Construct a new zoom axes.

        :param axes_of_zoom: The axes to zoom in on which this axes will be nested inside.
        :param rect: The bounding box to place this axes in, within the parent axes.
        :param transform: The transform to use when placing this axes in the parent axes. Defaults to
                          'axes_of_zoom.transData'.
        :param zorder: An integer, the z-order of the axes. Defaults to 5, which means it is drawn on top of most
                       object in the plot.
        :param kwargs: Any other keyword arguments which the Axes class accepts.
        """
        if(transform is None):
            transform = axes_of_zoom.transData

        inset_loc = _make_inset_locator(rect.bounds, transform, axes_of_zoom)
        bb = inset_loc(None, None)

        super().__init__(axes_of_zoom.figure, bb.bounds, zorder=zorder, **kwargs)

        self.__zoom_axes = axes_of_zoom
        self.zoom_ratio = zoom_ratio
        self.set_axes_locator(inset_loc)

        axes_of_zoom.add_child_axes(self)

    def draw(self, renderer=None, inframe=False):
        super().draw(renderer, inframe)

        if(not self.get_visible()):
            return

        axes_children = [
            *self.__zoom_axes.collections,
            *self.__zoom_axes.patches,
            *self.__zoom_axes.lines,
            *self.__zoom_axes.texts,
            *self.__zoom_axes.artists,
            *self.__zoom_axes.images
        ]

        for axes_child in axes_children:
            if isinstance(axes_child, Line2D):
                axes_child.set_markersize(axes_child.get_markersize() / self.zoom_ratio)
            if isinstance(axes_child, Text):
                axes_child.set_size(axes_child.get_size() / self.zoom_ratio)
            if isinstance(axes_child, PathCollection):
                axes_child.set_sizes(axes_child.get_sizes() / self.zoom_ratio ** 2)

        img_boxes = []
        # We need to temporarily disable the clip boxes of all of the images, in order to allow us to continue
        # rendering them it even if it is outside of the parent axes (they might still be visible in this zoom axes).
        for img in self.__zoom_axes.images:
            img_boxes.append(img.get_clip_box())
            img.set_clip_box(img.get_window_extent(renderer))

        # Sort all rendered item by their z-order so the render in layers correctly...
        axes_children.sort(key=lambda obj: obj.get_zorder())

        # Construct mock renderer and draw all artists to it.
        mock_renderer = TransformRenderer(renderer, self.__zoom_axes.transData, self.transData, self)

        for artist in axes_children:
            if(artist is not self):
                artist.draw(mock_renderer)

        # Reset all of the image clip boxes...
        for img, box in zip(self.__zoom_axes.images, img_boxes):
            img.set_clip_box(box)

        # We need to redraw the splines if enabled, as we have finally drawn everything... This avoids other objects
        # being drawn over the splines
        if(self.axison and self._frameon):
            for spine in self.spines.values():
                spine.draw(renderer)
