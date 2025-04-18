# Copyright (c) 2020, Matt Colligan. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
from collections import namedtuple

import cairocffi
import cairocffi.pixbuf

from libqtile.utils import scan_files


class LoadingError(Exception):
    pass


_SurfaceInfo = namedtuple("_SurfaceInfo", ("surface", "file_type"))


def get_cairo_surface(bytes_img, width=None, height=None):
    try:
        surf, fmt = cairocffi.pixbuf.decode_to_image_surface(bytes_img, width, height)
        return _SurfaceInfo(surf, fmt)
    except TypeError:
        from libqtile.log_utils import logger

        logger.exception(
            "Couldn't load cairo image at specified width and height. "
            "Falling back to image scaling using cairo. "
            "Need cairocffi > v0.8.0"
        )
        surf, fmt = cairocffi.pixbuf.decode_to_image_surface(bytes_img)
        return _SurfaceInfo(surf, fmt)


def get_cairo_pattern(surface, width=None, height=None, theta=0.0):
    """Return a SurfacePattern from an ImageSurface.

    if width and height are not None scale the pattern
    to be size width and height.

    theta is in degrees ccw
    """
    pattern = cairocffi.SurfacePattern(surface)
    pattern.set_filter(cairocffi.FILTER_BEST)
    matrix = cairocffi.Matrix()

    tr_width, tr_height = 1.0, 1.0
    surf_width, surf_height = surface.get_width(), surface.get_height()
    if (width is not None) and (width != surf_width):
        tr_width = surf_width / width
    if (height is not None) and (height != surf_height):
        tr_height = surf_height / height
    matrix.scale(tr_width, tr_height)

    epsilon = 1.0e-6
    pi = 3.141592653589793
    if abs(theta) > epsilon:
        theta_rad = pi / 180.0 * theta
        mat_rot = cairocffi.Matrix()
        # https://cairographics.org/cookbook/transform_about_point/
        xt = surf_width * tr_width * 0.5
        yt = surf_height * tr_height * 0.5
        mat_rot.translate(xt, yt)
        mat_rot.rotate(theta_rad)
        mat_rot.translate(-xt, -yt)
        matrix = mat_rot.multiply(matrix)

    pattern.set_matrix(matrix)
    return pattern


class _Descriptor:
    def __init__(self, name=None, default=None, **opts):
        self.name = name
        self.under_name = "_" + name
        self.default = default
        for key, value in opts.items():
            setattr(self, key, value)

    def __get__(self, obj, cls):
        if obj is None:
            return self
        _getattr = getattr
        try:
            return _getattr(obj, self.under_name)
        except AttributeError:
            return self.get_default(obj)

    def get_default(self, obj):
        return self.default

    def __set__(self, obj, value):
        setattr(obj, self.under_name, value)

    def __delete__(self, obj):
        delattr(obj, self.under_name)


class _Resetter(_Descriptor):
    def __set__(self, obj, value):
        super().__set__(obj, value)
        obj._reset()


class _PixelSize(_Resetter):
    def __set__(self, obj, value):
        value = max(round(value), 1)
        super().__set__(obj, value)

    def get_default(self, obj):
        size = obj.default_size
        return getattr(size, self.name)


class _Rotation(_Resetter):
    def __set__(self, obj, value):
        value = float(value)
        super().__set__(obj, value)


_ImgSize = namedtuple("_ImgSize", ("width", "height"))


class Img:
    """Img is a class which creates & manipulates cairo SurfacePatterns from an image

    There are two constructors Img(...) and Img.from_path(...)

    The cairo surface pattern is at img.pattern.
    Changing any of the attributes width, height, or theta will update the pattern.

    - width :: pattern width in pixels
    - height :: pattern height in pixels
    - theta :: rotation of pattern counter clockwise in degrees
    Pattern is first stretched, then rotated.
    """

    def __init__(self, bytes_img, name="", path=""):
        self.bytes_img = bytes_img
        self.name = name
        self.path = path

    def _reset(self):
        if hasattr(self, "surface"):
            self.surface.finish()
            del self.surface
        if hasattr(self, "pattern"):
            # patterns do not need to be finish()ed, only surfaces do
            del self.pattern

    @classmethod
    def from_path(cls, image_path):
        "Create an Img instance from image_path"
        with open(image_path, "rb") as fobj:
            bytes_img = fobj.read()
        name = os.path.basename(image_path)
        name, file_type = os.path.splitext(name)
        return cls(bytes_img, name=name, path=image_path)

    @property
    def default_surface(self):
        try:
            return self._default_surface
        except AttributeError:
            surf, fmt = get_cairo_surface(self.bytes_img)
            self._default_surface = surf
            return surf

    @property
    def default_size(self):
        try:
            return self._default_size
        except AttributeError:
            surf = self.default_surface
            size = _ImgSize(surf.get_width(), surf.get_height())
            self._default_size = size
            return size

    theta = _Rotation("theta", default=0.0)
    width = _PixelSize("width")
    height = _PixelSize("height")

    def resize(self, width=None, height=None):
        width0, height0 = self.default_size
        width_factor, height_factor = None, None
        if width is not None:
            width_factor = width / width0
        if height is not None:
            height_factor = height / height0

        if width and height:
            return self.scale(width_factor, height_factor, lock_aspect_ratio=False)
        if width or height:
            return self.scale(width_factor, height_factor, lock_aspect_ratio=True)
        raise ValueError("You must supply either width or height!")

    def scale(self, width_factor=None, height_factor=None, lock_aspect_ratio=False):
        if not (width_factor or height_factor):
            raise ValueError("You must supply width_factor or height_factor")
        if lock_aspect_ratio:
            res = self._scale_lock(width_factor, height_factor, self.default_size)
        else:
            res = self._scale_free(width_factor, height_factor, self.default_size)
        self.width, self.height = res

    @staticmethod
    def _scale_lock(width_factor, height_factor, initial_size):
        if width_factor and height_factor:
            raise ValueError(
                "Can't rescale with locked aspect ratio "
                "and give width_factor and height_factor."
                f" {width_factor}, {height_factor}"
            )
        width0, height0 = initial_size
        if width_factor:
            width = width0 * width_factor
            height = height0 / width0 * width
        else:
            height = height0 * height_factor
            width = width0 / height0 * height
        return _ImgSize(width, height)

    @staticmethod
    def _scale_free(width_factor, height_factor, initial_size):
        width_factor = 1 if width_factor is None else width_factor
        height_factor = 1 if height_factor is None else height_factor
        width0, height0 = initial_size
        return _ImgSize(width0 * width_factor, height0 * height_factor)

    @property
    def surface(self):
        try:
            return self._surface
        except AttributeError:
            surf, fmt = get_cairo_surface(self.bytes_img, self.width, self.height)
            self._surface = surf
            return surf

    @surface.deleter
    def surface(self):
        try:
            del self._surface
        except AttributeError:
            pass

    @property
    def pattern(self):
        try:
            return self._pattern
        except AttributeError:
            pat = get_cairo_pattern(self.surface, self.width, self.height, self.theta)
            self._pattern = pat
            return pat

    @pattern.deleter
    def pattern(self):
        try:
            del self._pattern
        except AttributeError:
            pass

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name!r}, {self.width}x{self.height}@{self.theta:.1f}deg, {self.path!r}>"

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        s0 = (self.bytes_img, self.theta, self.width, self.height)
        s1 = (other.bytes_img, other.theta, other.width, other.height)
        return s0 == s1


class Loader:
    """Loader - create Img() instances from image names

    load icons with Loader e.g.,
    >>> ldr = Loader('/usr/share/icons/Adwaita/24x24', '/usr/share/icons/Adwaita')
    >>> d_loaded_images = ldr('audio-volume-muted', 'audio-volume-low')
    """

    def __init__(self, *directories, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.directories = list(directories)

    def __call__(self, *names):
        d = {}
        seen = set()
        set_names = set()
        for n in names:
            root, ext = os.path.splitext(n)
            if ext:
                set_names.add(n)
            else:
                set_names.add(n + ".*")

        for directory in self.directories:
            d_matches = scan_files(directory, *(set_names - seen))
            for name, paths in d_matches.items():
                if paths:
                    d[name if name in names else name[:-2]] = Img.from_path(paths[0])
                    seen.add(name)

        if seen != set_names:
            msg = "Wasn't able to find images corresponding to the names: {}"
            raise LoadingError(msg.format(set_names - seen))

        return d
