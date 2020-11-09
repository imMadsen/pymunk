"""This module contain functions for automatic generation of geometry, for 
example from an image.

Example::

    >>> import pymunk
    >>> from pymunk.autogeometry import march_soft
    >>> img = [
    ...     "  xx   ",
    ...     "  xx   ",
    ...     "  xx   ",
    ...     "  xx   ",
    ...     "  xx   ",
    ...     "  xxxxx",
    ...     "  xxxxx",
    ... ]
    >>> segments = []

    >>> def segment_func(v0, v1):
    ...     segments.append((tuple(v0), tuple(v1)))
    >>> def sample_func(point):
    ...     x = int(point.x)
    ...     y = int(point.y)
    ...     return 1 if img[y][x] == "x" else 0

    >>> march_soft(pymunk.BB(0,0,6,6), 7, 7, .5, segment_func, sample_func)
    >>> print(len(segments))
    13

The information in segments can now be used to create geometry, for example as 
a Pymunk Poly or Segment::

    >>> s = pymunk.Space()
    >>> for (a,b) in segments:
    ...     segment = pymunk.Segment(s.static_body, a, b, 5)  
    ...     s.add(segment)


"""
__docformat__ = "reStructuredText"

from typing import TYPE_CHECKING, Callable, List, Sequence, Tuple, Union, overload

from ._chipmunk_cffi import ffi, lib
from .vec2d import Vec2d

if TYPE_CHECKING:
    from .bb import BB

_SegmentFunc = Callable[[Vec2d, Vec2d], None]
_SampleFunc = Callable[[Vec2d], float]


def _to_chipmunk(polyline) -> ffi.CData:
    l = len(polyline)
    _line = ffi.new("cpPolyline *", {"verts": l})
    _line.count = l
    _line.capacity = l
    _line.verts = polyline
    return _line


def _from_polyline_set(_set: ffi.CData) -> List[List[Vec2d]]:
    lines = []
    for i in range(_set.count):
        line = []
        l = _set.lines[i]
        for j in range(l.count):
            line.append(Vec2d(l.verts[j].x, l.verts[j].y))
        lines.append(line)
    return lines


def is_closed(polyline) -> bool:
    """Returns true if the first vertex is equal to the last.

    :param polyline: Polyline to simplify.
    :type polyline: [(float,float)]
    :rtype: `bool`
    """
    return bool(lib.cpPolylineIsClosed(_to_chipmunk(polyline)))


def simplify_curves(polyline, tolerance: float) -> List[Vec2d]:
    """Returns a copy of a polyline simplified by using the Douglas-Peucker
    algorithm.

    This works very well on smooth or gently curved shapes, but not well on
    straight edged or angular shapes.

    :param polyline: Polyline to simplify.
    :type polyline: [(float,float)]
    :param float tolerance: A higher value means more error is tolerated.
    :rtype: [(float,float)]
    """

    _line = lib.cpPolylineSimplifyCurves(_to_chipmunk(polyline), tolerance)
    simplified = []
    for i in range(_line.count):
        simplified.append(Vec2d(_line.verts[i].x, _line.verts[i].y))
    return simplified


def simplify_vertexes(polyline, tolerance) -> List[Vec2d]:
    """Returns a copy of a polyline simplified by discarding "flat" vertexes.

    This works well on straight edged or angular shapes, not as well on smooth
    shapes.

    :param polyline: Polyline to simplify.
    :type polyline: [(float,float)]
    :param float tolerance: A higher value means more error is tolerated.
    :rtype: [(float,float)]
    """
    _line = lib.cpPolylineSimplifyVertexes(_to_chipmunk(polyline), tolerance)
    simplified = []
    for i in range(_line.count):
        simplified.append(Vec2d(_line.verts[i].x, _line.verts[i].y))
    return simplified


def to_convex_hull(polyline, tolerance: float) -> List[Vec2d]:
    """Get the convex hull of a polyline as a looped polyline.

    :param polyline: Polyline to simplify.
    :type polyline: [(float,float)]
    :param float tolerance: A higher value means more error is tolerated.
    :rtype: [(float,float)]
    """
    _line = lib.cpPolylineToConvexHull(_to_chipmunk(polyline), tolerance)
    hull = []
    for i in range(_line.count):
        hull.append(Vec2d(_line.verts[i].x, _line.verts[i].y))
    return hull


def convex_decomposition(polyline, tolerance: float) -> List[List[Vec2d]]:
    """Get an approximate convex decomposition from a polyline.

    Returns a list of convex hulls that match the original shape to within
    tolerance.

    .. note::
        If the input is a self intersecting polygon, the output might end up
        overly simplified.

    :param polyline: Polyline to simplify.
    :type polyline: [(float,float)]
    :param float tolerance: A higher value means more error is tolerated.
    :rtype: [(float,float)]
    """
    _line = _to_chipmunk(polyline)
    _set = lib.cpPolylineConvexDecomposition(_line, tolerance)
    return _from_polyline_set(_set)


class PolylineSet(Sequence[List[Vec2d]]):
    """A set of Polylines.

    Mainly intended to be used for its :py:meth:`collect_segment` function
    when generating geometry with the :py:func:`march_soft` and
    :py:func:`march_hard` functions.
    """

    def __init__(self) -> None:
        def free(_set: ffi.CData) -> None:
            lib.cpPolylineSetFree(_set, True)

        self._set = ffi.gc(lib.cpPolylineSetNew(), free)

    def collect_segment(self, v0: Tuple[float, float], v1: Tuple[float, float]) -> None:
        """Add a line segment to a polyline set.

        A segment will either start a new polyline, join two others, or add to
        or loop an existing polyline. This is mostly intended to be used as a
        callback directly from :py:func:`march_soft` or :py:func:`march_hard`.

        :param v0: Start of segment
        :type v0: (float,float)
        :param v1: End of segment
        :type v1: (float,float)
        """
        assert len(v0) == 2
        assert len(v1) == 2

        lib.cpPolylineSetCollectSegment(v0, v1, self._set)

    def __len__(self) -> int:
        return self._set.count

    @overload
    def __getitem__(self, index: int) -> List[Vec2d]:
        ...

    @overload
    def __getitem__(self, index: slice) -> "PolylineSet":
        ...

    def __getitem__(self, key: Union[int, slice]) -> Union[List[Vec2d], "PolylineSet"]:
        assert not isinstance(key, slice), "Slice indexing not supported"
        if key >= self._set.count:
            raise IndexError
        line = []
        l = self._set.lines[key]
        for i in range(l.count):
            line.append(Vec2d(l.verts[i].x, l.verts[i].y))
        return line


def march_soft(
    bb: "BB",
    x_samples: int,
    y_samples: int,
    threshold: float,
    segment_func: _SegmentFunc,
    sample_func: _SampleFunc,
) -> None:
    """Trace an *anti-aliased* contour of an image along a particular threshold.

    The given number of samples will be taken and spread across the bounding
    box area using the sampling function and context.

    :param BB bb: Bounding box of the area to sample within
    :param int x_samples: Number of samples in x
    :param int y_samples: Number of samples in y
    :param float threshold: A higher value means more error is tolerated
    :param segment_func: The segment function will be called for each segment
        detected that lies along the density contour for threshold.
    :type segment_func: ``func(v0 : Vec2d, v1 : Vec2d)``
    :param sample_func: The sample function will be called for
        x_samples * y_samples spread across the bounding box area, and should
        return a float.
    :type sample_func: ``func(point: Vec2d) -> float``
    """

    @ffi.callback("cpMarchSegmentFunc")
    def _seg_f(v0: ffi.CData, v1: ffi.CData, _data: ffi.CData) -> None:
        segment_func(Vec2d(v0.x, v0.y), Vec2d(v1.x, v1.y))

    @ffi.callback("cpMarchSampleFunc")
    def _sam_f(point: ffi.CData, _data: ffi.CData) -> float:
        return sample_func(Vec2d(point.x, point.y))

    lib.cpMarchSoft(
        bb, x_samples, y_samples, threshold, _seg_f, ffi.NULL, _sam_f, ffi.NULL
    )


def march_hard(
    bb: "BB",
    x_samples: int,
    y_samples: int,
    threshold: float,
    segment_func: _SegmentFunc,
    sample_func: _SampleFunc,
) -> None:
    """Trace an *aliased* curve of an image along a particular threshold.

    The given number of samples will be taken and spread across the bounding
    box area using the sampling function and context.

    :param BB bb: Bounding box of the area to sample within
    :param int x_samples: Number of samples in x
    :param int y_samples: Number of samples in y
    :param float threshold: A higher value means more error is tolerated
    :param segment_func: The segment function will be called for each segment
        detected that lies along the density contour for threshold.
    :type segment_func: ``func(v0 : Vec2d, v1 : Vec2d)``
    :param sample_func: The sample function will be called for
        x_samples * y_samples spread across the bounding box area, and should
        return a float.
    :type sample_func: ``func(point: Vec2d) -> float``
    """

    @ffi.callback("cpMarchSegmentFunc")
    def _seg_f(v0: ffi.CData, v1: ffi.CData, _data: ffi.CData) -> None:
        segment_func(Vec2d(v0.x, v0.y), Vec2d(v1.x, v1.y))

    @ffi.callback("cpMarchSampleFunc")
    def _sam_f(point: ffi.CData, _data: ffi.CData) -> float:
        return sample_func(Vec2d(point.x, point.y))

    lib.cpMarchHard(
        bb, x_samples, y_samples, threshold, _seg_f, ffi.NULL, _sam_f, ffi.NULL
    )
